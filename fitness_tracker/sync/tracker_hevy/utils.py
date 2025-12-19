from bs4 import BeautifulSoup
import pandas as pd
from typing import Optional
from fitness_tracker.apis.hevy_app.types import PostRoutinesRequestSet

def get_workout_order(description: str):

    soup = BeautifulSoup(description, 'html.parser')

    name_and_info = soup.find('p', class_='name-and-info')
    if name_and_info is None:
        raise Exception("No workout elements found")
    
    # Get all text, splitting by the <br/> tags
    exercises: list[str] = [line.strip() for line in name_and_info.decode_contents().split('<br/>') if line.strip()] # type: ignore
    
    # Clean the lines to remove any residual HTML tags or spaces
    exercises = [BeautifulSoup(line, 'html.parser').text.strip() for line in exercises]

    order: dict[int, dict[str, str | int | None]] = {}
    for i, element in enumerate(exercises, start=1):
        key, value = element.split(') ')
        if key[-1].isdigit():
            # separate the numbers from the letters
            numbers = int(''.join([c for c in key if c.isdigit()]))
            letters = ''.join([c for c in key if not c.isdigit()])
            order[i] = {
                "exercise_name": value.strip(),
                "is_superset": True,
                "superset_group": letters,
                "superset_order": numbers,
                "identifier": key,
            }
        else:
            order[i] = {
                "exercise_name": value.strip(),
                "is_superset": False,
                "superset_group": None,
                "superset_order": None,
                "identifier": key,
            }

    

    return order

def get_superset_index(order: dict[int, dict[str, str | int | None]]) -> Optional[dict[str, int]]:
    df = pd.DataFrame(order).T
    df = df.loc[df['is_superset'] == True]
    if df.empty:
        return None
    df = df.groupby('superset_group', as_index=False).agg({'superset_order': 'max'}) # type: ignore
    df = df.reset_index().set_index('superset_group') # type: ignore
    return df['index'].to_dict()  # type: ignore

def create_notes(description: str) -> str:
    soup = BeautifulSoup(description, 'html.parser')

    workout_elements = soup.find('p', class_='name-and-info')
    if workout_elements is None:
        return ""
    
    return '\n'.join(workout_elements.stripped_strings)

def parse_sets(description: str) -> list[PostRoutinesRequestSet]:
    sets: list[PostRoutinesRequestSet] = [
        PostRoutinesRequestSet(
            type='normal',
            duration_seconds=60,
        )
        
    ]
    return sets
