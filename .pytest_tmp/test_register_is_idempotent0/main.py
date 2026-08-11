from fastapi import FastAPI

from app.features import auth, blog, home, orders

APPS = [home, blog, auth, orders]

app = FastAPI()
