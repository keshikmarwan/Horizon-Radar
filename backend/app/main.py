from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from app.api.routes import router

_backend_root = Path(__file__).resolve().parents[1]
load_dotenv(_backend_root / '.env', override=False)

app = FastAPI(title='Horizon Radar API', version='0.1.0')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(router, prefix='/api')

_static_dir = _backend_root / 'static'
if _static_dir.is_dir():
    app.mount('/', StaticFiles(directory=str(_static_dir), html=True), name='static')
