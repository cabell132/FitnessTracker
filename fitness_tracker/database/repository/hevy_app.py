from fitness_tracker.database.repository.base import BaseRepository
from fitness_tracker.database.models.hevy_app import *
from sqlalchemy.orm import Session

class HevyAppWorkoutRepository(BaseRepository[HevyAppWorkout]):
    """True Coach repository class"""
    
    def __init__(self, session:Session) -> None:
        """Initiate the True Coach repository with the session
        
        """
        super().__init__(session=session, model_class=HevyAppWorkout)

class HevyAppWorkoutItemRepository(BaseRepository[HevyAppWorkoutItem]):
    """True Coach repository class"""
    
    def __init__(self, session:Session) -> None:
        """Initiate the True Coach repository with the session
        
        """
        super().__init__(session=session, model_class=HevyAppWorkoutItem)

class HevyAppSetsRepository(BaseRepository[HevyAppSets]):
    """True Coach repository class"""
    
    def __init__(self, session:Session) -> None:
        """Initiate the True Coach repository with the session
        
        """
        super().__init__(session=session, model_class=HevyAppSets)
        
class HevyAppExerciseRepository(BaseRepository[HevyAppExercise]):
    """True Coach repository class"""
    
    def __init__(self, session:Session) -> None:
        """Initiate the True Coach repository with the session
        
        """
        super().__init__(session=session, model_class=HevyAppExercise)
        
class HevyAppActivatedMuscleRepository(BaseRepository[HevyAppActivatedMuscle]):
    """True Coach repository class"""
    
    def __init__(self, session:Session) -> None:
        """Initiate the True Coach repository with the session
        
        """
        super().__init__(session=session, model_class=HevyAppActivatedMuscle)

