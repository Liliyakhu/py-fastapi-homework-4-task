from datetime import date

from fastapi import UploadFile, Form, File, HTTPException
from pydantic import BaseModel, ConfigDict

from validation import (
    validate_name,
    validate_image,
    validate_gender,
    validate_birth_date
)


class ProfileCreateSchema:
    def __init__(
            self,
            first_name: str = Form(...),
            last_name: str = Form(...),
            gender: str = Form(...),
            date_of_birth: date = Form(...),
            info: str = Form(...),
            avatar: UploadFile = File(...)
    ):
        try:
            validate_name(first_name)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        self.first_name = first_name.lower()

        try:
            validate_name(last_name)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        self.last_name = last_name.lower()

        try:
            validate_gender(gender)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        self.gender = gender

        try:
            validate_birth_date(date_of_birth)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        self.date_of_birth = date_of_birth

        try:
            if not info or not info.strip():
                raise ValueError("Info field cannot be empty or contain only spaces.")
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        self.info = info

        try:
            validate_image(avatar)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        avatar.file.seek(0)
        self.avatar = avatar


class ProfileResponseSchema(BaseModel):
    id: int
    user_id: int
    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    info: str
    avatar: str

    model_config = ConfigDict(from_attributes=True)
