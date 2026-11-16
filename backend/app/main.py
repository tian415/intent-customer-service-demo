"""Application factory: tests use isolated databases; normal startup migrates locally."""
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm.exc import StaleDataError
from app.api import admin, auth, catalog, conversations, health, orders, tickets
from app.database import DATABASE_PATH, make_engine, migrate
from app.security import hash_password


def create_app(database_path: Path | None = None, model_path: Path | None = None, *, expected_model_sha256: str | None = None, label_map_path: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        engine = make_engine(database_path or DATABASE_PATH)
        migrate(engine)
        application.state.engine = engine
        application.state.model_path = model_path
        application.state.expected_model_sha256 = expected_model_sha256
        application.state.label_map_path = label_map_path
        application.state.dummy_hash = hash_password(secrets.token_urlsafe(32))
        yield
        engine.dispose()

    application = FastAPI(title='智能客服工单管理系统', version='0.2.0', lifespan=lifespan)

    application.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])

    @application.middleware('http')
    async def browser_boundary(request: Request, call_next):
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            origin = request.headers.get('origin')
            host = request.headers.get('host', '')
            if origin:
                try:
                    parsed = urlsplit(origin)
                    valid_origin = parsed.netloc == host and parsed.scheme in ('http', 'https')
                except ValueError:
                    valid_origin = False
                if not valid_origin:
                    return JSONResponse({'detail': '拒绝跨来源写请求'}, status_code=403)
            if request.headers.get('X-Requested-With') != 'ticket-ui':
                return JSONResponse({'detail': '缺少请求来源校验'}, status_code=403)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        return response

    @application.exception_handler(IntegrityError)
    async def integrity_error(_request, _exc):
        return JSONResponse({'detail': '记录名称已存在或关联记录不合法'}, status_code=409)

    @application.exception_handler(StaleDataError)
    async def stale_error(_request, _exc):
        return JSONResponse({'detail': '工单已被更新，请刷新详情后重试'}, status_code=409)

    @application.exception_handler(OperationalError)
    async def database_error(_request, exc):
        if 'locked' in str(exc.orig).lower():
            return JSONResponse({'detail': '数据库繁忙，请稍后重试'}, status_code=503)
        raise exc

    for router in (health.router, auth.router, admin.router, tickets.router, catalog.router, orders.router, conversations.router):
        application.include_router(router, prefix='/api')
    return application


app = create_app(model_path=Path(os.environ['INTENT_MODEL_PATH']) if os.environ.get('INTENT_MODEL_PATH') else None,
                 expected_model_sha256=os.environ.get('INTENT_MODEL_SHA256'),
                 label_map_path=Path(os.environ['INTENT_LABEL_MAP_PATH']) if os.environ.get('INTENT_LABEL_MAP_PATH') else None)
