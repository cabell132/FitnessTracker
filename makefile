change-python-version:
	@pyenv local $(v)
	@uv venv --python $(v)
	@.venv\Scripts\activate
	@uv sync

# update database schema
update-schema:
	alembic revision --autogenerate
	alembic upgrade head