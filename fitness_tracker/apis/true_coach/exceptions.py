from typing import Optional
import logs

logger = logs.get_logger(__name__)


class TrueCoachAPIError(Exception):
    """True Coach API error"""

    url: str
    status_code: Optional[int] = None

    def __init__(
        self, message: str, url: str, status_code: Optional[int] = None
    ) -> None:
        """Initiate the error"""
        super().__init__(message)
        self.status_code = status_code
        self.url = url

        logger.error(
            f"True Coach API Error: {message} (status_code={status_code}, url={url})"
        )
