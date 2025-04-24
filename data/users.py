from datetime import datetime

import sqlalchemy
from sqlalchemy import orm

from .db_session import SqlAlchemyBase


class User(SqlAlchemyBase):
    __tablename__ = 'users'
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    account_id = sqlalchemy.Column(sqlalchemy.Integer)

    nickname = sqlalchemy.Column(sqlalchemy.String)

    surname = sqlalchemy.Column(sqlalchemy.String, nullable=True, default=None)
    name = sqlalchemy.Column(sqlalchemy.String, nullable=True, default=None)

    modified_date = sqlalchemy.Column(sqlalchemy.DateTime, default=datetime.now)
    logging = orm.relationship("Logging", back_populates='user')

    def __repr__(self):
        return self.nickname
