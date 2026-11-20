"""Pydantic data models shared across layers."""

from my_agent.schemas.annotation import Annotation, SceneType
from my_agent.schemas.exif import ExifData, GpsCoordinate
from my_agent.schemas.photo import PhotoRecord

__all__ = ["Annotation", "ExifData", "GpsCoordinate", "PhotoRecord", "SceneType"]
