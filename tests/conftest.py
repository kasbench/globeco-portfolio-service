import pytest
from testcontainers.mongodb import MongoDbContainer
import os

@pytest.fixture(scope="session")
def mongodb_container():
    with MongoDbContainer("mongo:8.0.9") as mongo:
        os.environ["MONGODB_URI"] = mongo.get_connection_url()
        yield mongo 