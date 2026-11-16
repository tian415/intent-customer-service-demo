"""Explicit local database/bootstrap commands; never resets existing records."""
import argparse
import getpass
import json
import os
import secrets
from pathlib import Path
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.engine import Engine
from app.services.refunds import POLICY_HELP
from app.database import DATABASE_PATH, ROOT, make_engine, migrate
from app.models import Category, FAQ, Group, Order, User, AuthSession, now
from app.schemas import UserCreate
from app.services.admin import save_user
from app.security import hash_password, invalidate_sessions


DEMO_IDENTITIES = {'demo_admin': ('DEMO 管理员', 'admin'), 'demo_agent': ('DEMO 客服一', 'agent'),
                   'demo_agent2': ('DEMO 客服二', 'agent'), 'demo_user': ('DEMO 用户', 'user')}


def rotate_demo(engine: Engine, output: Path) -> dict:
    """Rotate only recognizable seed accounts; never return or print passwords."""
    if output.exists():
        raise ValueError('凭据输出已存在，拒绝覆盖')
    created = False
    with Session(engine) as db:
        db.connection().exec_driver_sql('BEGIN IMMEDIATE')
        users = list(db.scalars(select(User).where(User.username.in_(DEMO_IDENTITIES))))
        if len(users) != len(DEMO_IDENTITIES) or any((u.display_name, u.role) != DEMO_IDENTITIES[u.username] for u in users):
            raise ValueError('DEMO账号不完整或演示身份已变更，拒绝轮换')
        credentials = {u.username: secrets.token_urlsafe(24) for u in users}
        hashes = {name: hash_password(password) for name, password in credentials.items()}
        ids = [u.id for u in users]
        revoked = db.scalar(select(func.count()).select_from(AuthSession).where(AuthSession.user_id.in_(ids)))
        try:
            new_directories = []
            directory = output.parent
            while not directory.exists():
                new_directories.append(directory)
                directory = directory.parent
            output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created = True
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                json.dump({'purpose': 'private local DEMO credentials; do not share or commit', 'credentials': credentials}, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            # Persist the file entry and any newly created parent entries before auth changes.
            for directory in dict.fromkeys([output.parent, *(p.parent for p in new_directories)]):
                descriptor = os.open(directory, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            for user in users:
                user.password_hash = hashes[user.username]
                invalidate_sessions(db, user.id)
            db.commit()
        except Exception:
            db.rollback()
            if created:
                output.unlink()
            raise
    return {'rotated_accounts': len(users), 'revoked_sessions': revoked, 'credentials_file': str(output)}


def seed_demo_orders(db: Session, user_id: int) -> int:
    """Idempotent local mock orders for a DEMO user; never invents research labels."""
    existing = db.scalar(select(func.count()).select_from(Order).where(Order.user_id == user_id))
    if existing:
        return 0
    samples = [
        ('DEMO20261103001', '无线蓝牙耳机', 'shipped', 12900),
        ('DEMO20261103002', '保温杯 500ml', 'delivered', 5900),
        ('DEMO20261103003', '机械键盘套件', 'refunding', 29900),
    ]
    stamp = now()
    for order_no, product_name, status, amount in samples:
        db.add(Order(user_id=user_id, order_no=order_no, product_name=product_name, status=status, amount_cents=amount, created_at=stamp, updated_at=stamp))
    return len(samples)


def ensure_demo_orders(db: Session) -> int:
    demo_user = db.scalar(select(User).where(User.username == 'demo_user', User.role == 'user'))
    if not demo_user:
        return 0
    added = seed_demo_orders(db, demo_user.id)
    if added:
        db.commit()
    return added


def seed_demo(db: Session) -> list[tuple[str, str]]:
    if db.scalar(select(func.count()).select_from(User)):
        return []
    group = Group(name='DEMO 综合客服组')
    db.add(group)
    db.flush()
    credentials = []
    demo_user_id = None
    for username, name, role in [('demo_admin', 'DEMO 管理员', 'admin'), ('demo_agent', 'DEMO 客服一', 'agent'), ('demo_agent2', 'DEMO 客服二', 'agent'), ('demo_user', 'DEMO 用户', 'user')]:
        password = secrets.token_urlsafe(18)
        user = save_user(db, UserCreate(username=username, display_name=name, password=password, role=role, active=True, group_id=group.id if role == 'agent' else None))
        credentials.append((username, password))
        if username == 'demo_user':
            demo_user_id = user.id
    categories = [Category(name='账号问题', keywords='登录,密码,账号', group_id=group.id), Category(name='退款咨询', keywords='退款,退费', group_id=group.id), Category(name='产品故障', keywords='报错,故障,闪退', group_id=group.id)]
    db.add_all(categories)
    db.flush()
    db.add(FAQ(question='DEMO：忘记密码怎么办？', answer='DEMO 演示知识：请联系管理员重设本系统账号密码。此答案用于工程演示，不代表外部企业政策。', keywords='密码', category_id=categories[0].id))
    db.add(FAQ(question='DEMO：如何咨询退款？', answer=POLICY_HELP, keywords='退款,退费', category_id=categories[1].id))
    if demo_user_id is not None:
        seed_demo_orders(db, demo_user_id)
    db.commit()
    return credentials


def main() -> None:
    parser = argparse.ArgumentParser(description='本地数据库迁移和账号初始化')
    parser.add_argument('command', choices=['migrate', 'init-admin', 'demo', 'rotate-demo'])
    parser.add_argument('--database', type=Path, default=DATABASE_PATH)
    parser.add_argument('--output', type=Path, help='rotate-demo必须指定私有新文件；密码不输出到终端')
    args = parser.parse_args()
    if args.command == 'rotate-demo' and (not args.output or not args.database.is_file()):
        parser.error('rotate-demo需要已存在数据库及--output私有新文件')
    if args.command == 'rotate-demo' and not args.output.resolve().is_relative_to(ROOT / 'data/private'):
        parser.error('轮换凭据只能保存到被忽略的项目data/private目录')
    engine = make_engine(args.database)
    try:
        if args.command == 'rotate-demo':
            result = rotate_demo(engine, args.output)
            print(json.dumps(result, ensure_ascii=False))
            return
        versions = migrate(engine)
        print('迁移完成：' + (', '.join(versions) or '版本已是最新，未修改结构'))
        if args.command == 'migrate':
            return
        with Session(engine, expire_on_commit=False) as db:
            db.connection().exec_driver_sql('BEGIN IMMEDIATE')
            if args.command == 'demo':
                credentials = seed_demo(db)
                if not credentials:
                    added = ensure_demo_orders(db)
                    if added:
                        print(f'已为 demo_user 补充 {added} 笔本机演示订单；未改动账号密码。')
                    else:
                        print('已有账号，跳过 DEMO 初始化；未覆盖密码或数据。')
                else:
                    print('DEMO 工程演示账号（非真实用户/训练数据），随机密码仅显示本次：')
                    for username, password in credentials:
                        print(f'{username}: {password}')
                return
            if db.scalar(select(func.count()).select_from(User).where(User.role == 'admin', User.active.is_(True))):
                raise SystemExit('已有有效管理员，请登录后台管理账号。')
            username = input('管理员账号（3–40 位 ASCII 字母数字/_ . -）：').strip()
            password = getpass.getpass('密码（12–128 位，不回显）：')
            if password != getpass.getpass('再次输入密码：'):
                raise SystemExit('密码不一致，未创建账号。')
            save_user(db, UserCreate(username=username, display_name='管理员', role='admin', password=password))
            db.commit()
            print('管理员创建成功；使用该账号登录并创建业务账号。')
    except (ValueError, OSError) as exc:
        parser.exit(2, f'操作失败：{exc}\n')
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
