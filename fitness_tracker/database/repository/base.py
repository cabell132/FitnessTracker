from collections.abc import Sequence
from typing import Any, Generic, Optional, TypeVar

import logs
from fitness_tracker.database.models.base import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

T = TypeVar("T", bound=BaseModel)

logger = logs.get_logger(__name__)


class BaseRepository(Generic[T]):
    """Base repository class to be inherited by all other repositories."""

    def __init__(
        self,
        session: Session,
        model_class: type[T],
    ):
        """Initialize the repository class.

        Args:
            session: The session to use for the repository.
            model_class: The model class to use for the repository.
        """
        self.model_class = model_class
        self.session = session

    def query(self, *entities: Any, **kwargs: Any):
        """Function to create for the given entities.

        Args:
            *entities: The entities to query.
            **kwargs: The query parameters.

        Returns:
            The query object.

        Example:
            >>> query = self.query(ArtistModel)

        Query the `name` column of the `ArtistModel` table:
            >>> query = self.query(ArtistModel.name)
        """
        query = self.session.query(*entities)
        if kwargs:
            query = query.filter_by(**kwargs)  # type: ignore
        return query

    def get(self, **kwargs: Any) -> Optional[T]:
        """Function to return a record of a model class by kwargs.

        Args:
            **kwargs: The kwargs of the record to return.

        Returns:
            A record of a model class.
        """
        return self.query(self.model_class, **kwargs).first()  # type: ignore

    def get_all(self, **kwargs: Any) -> list[T]:
        """Function to return all records of a model class.

        Args:
            **kwargs: The kwargs of the record to return.

        Returns:
        All records of a model class.
        """
        return self.query(self.model_class, **kwargs).all()  # type: ignore

    def exists(self, **kwargs: Any) -> bool:
        """Function to return a record of a model class by kwargs.

        :param kwargs: The kwargs of the record to return
        :type kwargs: dict

        :return: A record of a model class
        :rtype: Optional[Base]
        """
        return self.get(**kwargs) is not None

    def exists_list(self, **kwargs: Any) -> Sequence[bool]:
        """Function to check if a record exists in the database based on the given kwargs.

        :param kwargs: kwargs to filter the records by with the format {column_name: [value1, value2, ...]}
        :type kwargs: dict

        :return: A list of boolean values indicating whether the records exist or not.
        :rtype: Sequence[bool]
        """  # noqa: W505
        results: Sequence[bool] = []
        for key, values in kwargs.items():
            for value in values:
                results.append(self.exists(**{key: value}))
        return results

    def add(self, obj: T):
        """Function to add a record to the database.

        :param obj: The record to add to the database
        :type obj: Base

        :return: The added record
        :rtype: Base
        """
        self.session.add(obj)  # type: ignore
        logger.debug("Added %s to the database", obj)

    def merge(self, obj: T):
        """Function to merge a record to the database.

        :param obj: The record to merge to the database
        :type obj: Base

        :return: The merged record
        :rtype: Base
        """
        self.session.merge(obj)  # type: ignore

    def insert_ignore(self, obj: T) -> None:
        """Function to add a record to the database if it doesn't already exist.

        Args:
            obj: The record to add to the database.
        """
        if getattr(obj, "date_created", None) is None:
            obj.date_created = func.now()
        if getattr(obj, "date_updated", None) is None:
            obj.date_updated = func.now()
        stmnt = obj.insert_ignore()
        self.session.execute(stmnt)  # type: ignore

    def delete(self, obj: T) -> None:
        """Function to delete a record from the database.

        :param obj: The record to delete from the database
        :type obj: Base
        """
        self.session.delete(obj)  # type: ignore
        logger.debug("Deleted %s from the database", obj)

    def delete_all(self, **kwargs: Any) -> None:
        """Function to delete a record from the database by id.

        :param kwargs: The kwargs of the record to delete from the database
        :type kwargs: dict
        """
        recs = self.get_all(**kwargs)
        for rec in recs:
            self.delete(rec)
