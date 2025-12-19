change-python-version:
	@pyenv local $(v)
	@for /f "delims=" %%i in ('pyenv which python') do @poetry env use %%i
	@.venv\Scripts\activate
	@poetry update

# update database schema
update-schema:
	alembic revision --autogenerate
	alembic upgrade head