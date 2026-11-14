"""Shared account bounds: reject invalid input before hashing or database writes."""

from typing import Annotated

from pydantic import StringConstraints

Username = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=50, pattern=r"^[^\x00-\x1f\x7f]+$"
    ),
]
PersonName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=100, pattern=r"^[^\x00-\x1f\x7f]+$"
    ),
]
Password = Annotated[str, StringConstraints(min_length=8, max_length=1024)]
