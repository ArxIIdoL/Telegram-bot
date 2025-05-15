from datetime import datetime

import sqlalchemy
from sqlalchemy import orm

from .db_session import SqlAlchemyBase


class Logging(SqlAlchemyBase):
    __tablename__ = 'logging'
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    applying_user = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"))
    request = sqlalchemy.Column(sqlalchemy.String, nullable=True)
    request_date = sqlalchemy.Column(sqlalchemy.DateTime, default=datetime.now)
    user = orm.relationship('User')

    def __repr__(self):
        return (f'Обратившийся пользователь:- {self.user.nickname}'
                f'Дата запроса:- {self.request_date}'
                f'Запрос:- {self.request}')
