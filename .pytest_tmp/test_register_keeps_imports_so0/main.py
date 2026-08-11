from fastapi import FastAPI

from app.features import aardvark, auth, blog, home

APPS = [home, blog, auth, aardvark]

app = FastAPI()
