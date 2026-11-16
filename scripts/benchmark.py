"""Local API smoke benchmark with disposable DEMO records, never research metrics."""
from pathlib import Path
import json
import statistics
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.main import create_app
from app.models import Ticket, User
from app.security import hash_password


def main() -> None:
    (ROOT / '.cache').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='benchmark-', dir=ROOT / '.cache') as temp:
        app = create_app(Path(temp) / 'benchmark.sqlite3')
        with TestClient(app, headers={'X-Requested-With': 'ticket-ui'}) as client:
            with Session(app.state.engine) as db:
                user = User(username='benchmark', display_name='DEMO 基准用户', role='user', active=True, password_hash=hash_password('DEMO-benchmark-password'))
                db.add(user)
                db.flush()
                db.add_all([Ticket(title=f'DEMO 性能工单 {i}', description='合成工程负载，不是业务成果', owner_id=user.id, status='pending', prediction_source='fallback', needs_manual=True) for i in range(1000)])
                db.commit()
            response = client.post('/api/auth/login', json={'username': 'benchmark', 'password': 'DEMO-benchmark-password'})
            assert response.status_code == 200
            samples = []
            for index in range(55):
                started = time.perf_counter()
                response = client.get('/api/tickets?q=DEMO&page=1&page_size=20')
                elapsed = (time.perf_counter() - started) * 1000
                assert response.status_code == 200
                assert response.json()['total'] == 1000 and len(response.json()['items']) == 20
                if index >= 5:
                    samples.append(elapsed)
            print(json.dumps({'purpose': 'DEMO local engineering smoke, not capacity SLA or research result', 'records': 1000, 'requests': len(samples), 'warmup': 5, 'median_ms': round(statistics.median(samples), 2), 'p95_ms': round(sorted(samples)[47], 2), 'max_ms': round(max(samples), 2)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
