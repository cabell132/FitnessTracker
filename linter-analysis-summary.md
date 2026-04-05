# Linter report summary

Generated from `linter-analysis-output.txt`.

## Totals by tool


| Tool               | Issues   | Files affected |
| ------------------ | -------- | -------------- |
| pip_audit          | 11       | 11             |
| pydoclint          | 383      | 35             |
| ruff_check         | 673      | 62             |
| ruff_format        | 33       | 33             |
| slop_detector      | 11       | 7              |
| sloppylint         | 5        | 5              |
| ty                 | 85       | 19             |
| **combined (sum)** | **1201** | **80**         |


## Combined tree (directories + files, depth-first)


| Path                                                  | Kind      | Issues (rollup for dirs) | Subdirs | Files here |
| ----------------------------------------------------- | --------- | ------------------------ | ------- | ---------- |
| `fitness_tracker`                                     | directory | 1179                     | 4       | 0          |
| `fitness_tracker/apis`                                | directory | 419                      | 2       | 2          |
| `fitness_tracker/apis/hevy_app`                       | directory | 210                      | 0       | 9          |
| `fitness_tracker/apis/hevy_app/__init__.py`           | file      | 3                        | 0       | 0          |
| `fitness_tracker/apis/hevy_app/client.py`             | file      | 3                        | 0       | 0          |
| `fitness_tracker/apis/hevy_app/exceptions.py`         | file      | 9                        | 0       | 0          |
| `fitness_tracker/apis/hevy_app/exercises.py`          | file      | 12                       | 0       | 0          |
| `fitness_tracker/apis/hevy_app/routines.py`           | file      | 26                       | 0       | 0          |
| `fitness_tracker/apis/hevy_app/session.py`            | file      | 41                       | 0       | 0          |
| `fitness_tracker/apis/hevy_app/types.py`              | file      | 45                       | 0       | 0          |
| `fitness_tracker/apis/hevy_app/web_session.py`        | file      | 37                       | 0       | 0          |
| `fitness_tracker/apis/hevy_app/workouts.py`           | file      | 34                       | 0       | 0          |
| `fitness_tracker/apis/true_coach`                     | directory | 203                      | 0       | 9          |
| `fitness_tracker/apis/true_coach/__init__.py`         | file      | 3                        | 0       | 0          |
| `fitness_tracker/apis/true_coach/assessments.py`      | file      | 15                       | 0       | 0          |
| `fitness_tracker/apis/true_coach/auth.py`             | file      | 41                       | 0       | 0          |
| `fitness_tracker/apis/true_coach/client.py`           | file      | 6                        | 0       | 0          |
| `fitness_tracker/apis/true_coach/exceptions.py`       | file      | 9                        | 0       | 0          |
| `fitness_tracker/apis/true_coach/exercises.py`        | file      | 16                       | 0       | 0          |
| `fitness_tracker/apis/true_coach/session.py`          | file      | 40                       | 0       | 0          |
| `fitness_tracker/apis/true_coach/types.py`            | file      | 55                       | 0       | 0          |
| `fitness_tracker/apis/true_coach/workouts.py`         | file      | 18                       | 0       | 0          |
| `fitness_tracker/apis/__init__.py`                    | file      | 4                        | 0       | 0          |
| `fitness_tracker/apis/base.py`                        | file      | 2                        | 0       | 0          |
| `fitness_tracker/database`                            | directory | 457                      | 3       | 2          |
| `fitness_tracker/database/models`                     | directory | 92                       | 0       | 6          |
| `fitness_tracker/database/models/__init__.py`         | file      | 6                        | 0       | 0          |
| `fitness_tracker/database/models/apple_health.py`     | file      | 7                        | 0       | 0          |
| `fitness_tracker/database/models/base.py`             | file      | 42                       | 0       | 0          |
| `fitness_tracker/database/models/hevy_app.py`         | file      | 15                       | 0       | 0          |
| `fitness_tracker/database/models/tracker.py`          | file      | 4                        | 0       | 0          |
| `fitness_tracker/database/models/true_coach.py`       | file      | 18                       | 0       | 0          |
| `fitness_tracker/database/repository`                 | directory | 130                      | 0       | 6          |
| `fitness_tracker/database/repository/__init__.py`     | file      | 4                        | 0       | 0          |
| `fitness_tracker/database/repository/apple_health.py` | file      | 10                       | 0       | 0          |
| `fitness_tracker/database/repository/base.py`         | file      | 46                       | 0       | 0          |
| `fitness_tracker/database/repository/hevy_app.py`     | file      | 50                       | 0       | 0          |
| `fitness_tracker/database/repository/tracker.py`      | file      | 1                        | 0       | 0          |
| `fitness_tracker/database/repository/true_coach.py`   | file      | 19                       | 0       | 0          |
| `fitness_tracker/database/services`                   | directory | 222                      | 0       | 6          |
| `fitness_tracker/database/services/__init__.py`       | file      | 1                        | 0       | 0          |
| `fitness_tracker/database/services/apple_health.py`   | file      | 35                       | 0       | 0          |
| `fitness_tracker/database/services/base.py`           | file      | 13                       | 0       | 0          |
| `fitness_tracker/database/services/hevy_app.py`       | file      | 59                       | 0       | 0          |
| `fitness_tracker/database/services/tracker.py`        | file      | 25                       | 0       | 0          |
| `fitness_tracker/database/services/true_coach.py`     | file      | 89                       | 0       | 0          |
| `fitness_tracker/database/__init__.py`                | file      | 3                        | 0       | 0          |
| `fitness_tracker/database/connection.py`              | file      | 10                       | 0       | 0          |
| `fitness_tracker/llm`                                 | directory | 60                       | 0       | 5          |
| `fitness_tracker/llm/__init__.py`                     | file      | 4                        | 0       | 0          |
| `fitness_tracker/llm/fitness_llm.py`                  | file      | 22                       | 0       | 0          |
| `fitness_tracker/llm/open_ai_llm.py`                  | file      | 16                       | 0       | 0          |
| `fitness_tracker/llm/prompt_models.py`                | file      | 13                       | 0       | 0          |
| `fitness_tracker/llm/prompt_templates.py`             | file      | 5                        | 0       | 0          |
| `fitness_tracker/sync`                                | directory | 243                      | 7       | 3          |
| `fitness_tracker/sync/apple_health_tracker`           | directory | 26                       | 0       | 2          |
| `fitness_tracker/sync/apple_health_tracker/sync.py`   | file      | 24                       | 0       | 0          |
| `fitness_tracker/sync/apple_health_tracker/utils.py`  | file      | 2                        | 0       | 0          |
| `fitness_tracker/sync/hevy_tracker`                   | directory | 52                       | 0       | 2          |
| `fitness_tracker/sync/hevy_tracker/sync.py`           | file      | 50                       | 0       | 0          |
| `fitness_tracker/sync/hevy_tracker/utils.py`          | file      | 2                        | 0       | 0          |
| `fitness_tracker/sync/hevy_true_coach`                | directory | 24                       | 0       | 2          |
| `fitness_tracker/sync/hevy_true_coach/sync.py`        | file      | 14                       | 0       | 0          |
| `fitness_tracker/sync/hevy_true_coach/utils.py`       | file      | 10                       | 0       | 0          |
| `fitness_tracker/sync/tracker_hevy`                   | directory | 47                       | 0       | 2          |
| `fitness_tracker/sync/tracker_hevy/sync.py`           | file      | 25                       | 0       | 0          |
| `fitness_tracker/sync/tracker_hevy/utils.py`          | file      | 22                       | 0       | 0          |
| `fitness_tracker/sync/tracker_true_coach`             | directory | 36                       | 0       | 2          |
| `fitness_tracker/sync/tracker_true_coach/sync.py`     | file      | 14                       | 0       | 0          |
| `fitness_tracker/sync/tracker_true_coach/utils.py`    | file      | 22                       | 0       | 0          |
| `fitness_tracker/sync/true_coach_hevy`                | directory | 36                       | 0       | 2          |
| `fitness_tracker/sync/true_coach_hevy/sync.py`        | file      | 20                       | 0       | 0          |
| `fitness_tracker/sync/true_coach_hevy/utils.py`       | file      | 16                       | 0       | 0          |
| `fitness_tracker/sync/true_coach_tracker`             | directory | 14                       | 0       | 2          |
| `fitness_tracker/sync/true_coach_tracker/sync.py`     | file      | 12                       | 0       | 0          |
| `fitness_tracker/sync/true_coach_tracker/utils.py`    | file      | 2                        | 0       | 0          |
| `fitness_tracker/sync/__init__.py`                    | file      | 4                        | 0       | 0          |
| `fitness_tracker/sync/base.py`                        | file      | 1                        | 0       | 0          |
| `fitness_tracker/sync/sync.py`                        | file      | 3                        | 0       | 0          |
| `(dependency) filelock`                               | file      | 1                        | 0       | 0          |
| `(dependency) langchain-core`                         | file      | 1                        | 0       | 0          |
| `(dependency) langgraph`                              | file      | 1                        | 0       | 0          |
| `(dependency) langgraph-checkpoint`                   | file      | 1                        | 0       | 0          |
| `(dependency) langsmith`                              | file      | 1                        | 0       | 0          |
| `(dependency) orjson`                                 | file      | 1                        | 0       | 0          |
| `(dependency) pillow`                                 | file      | 1                        | 0       | 0          |
| `(dependency) pygments`                               | file      | 1                        | 0       | 0          |
| `(dependency) requests`                               | file      | 1                        | 0       | 0          |
| `(dependency) urllib3`                                | file      | 1                        | 0       | 0          |
| `(dependency) virtualenv`                             | file      | 1                        | 0       | 0          |
| `(slop-detector) apple_health.py`                     | file      | 1                        | 0       | 0          |
| `(slop-detector) base.py`                             | file      | 2                        | 0       | 0          |
| `(slop-detector) hevy_app.py`                         | file      | 1                        | 0       | 0          |
| `(slop-detector) sync.py`                             | file      | 1                        | 0       | 0          |
| `(slop-detector) tracker.py`                          | file      | 1                        | 0       | 0          |
| `(slop-detector) true_coach.py`                       | file      | 1                        | 0       | 0          |
| `(slop-detector) utils.py`                            | file      | 4                        | 0       | 0          |


Per-tool rollups live in `rollups.by_linter` in the JSON file.

## Per-tool top files (up to 15 each)

### pip_audit


| File                                | Issues |
| ----------------------------------- | ------ |
| `(dependency) filelock`             | 1      |
| `(dependency) langchain-core`       | 1      |
| `(dependency) langgraph`            | 1      |
| `(dependency) langgraph-checkpoint` | 1      |
| `(dependency) langsmith`            | 1      |
| `(dependency) orjson`               | 1      |
| `(dependency) pillow`               | 1      |
| `(dependency) pygments`             | 1      |
| `(dependency) requests`             | 1      |
| `(dependency) urllib3`              | 1      |
| `(dependency) virtualenv`           | 1      |


### pydoclint


| File                                                | Issues |
| --------------------------------------------------- | ------ |
| `fitness_tracker/database/services/true_coach.py`   | 48     |
| `fitness_tracker/database/repository/base.py`       | 31     |
| `fitness_tracker/database/services/hevy_app.py`     | 28     |
| `fitness_tracker/database/models/base.py`           | 22     |
| `fitness_tracker/database/services/apple_health.py` | 22     |
| `fitness_tracker/apis/hevy_app/session.py`          | 17     |
| `fitness_tracker/apis/hevy_app/web_session.py`      | 17     |
| `fitness_tracker/sync/hevy_tracker/sync.py`         | 17     |
| `fitness_tracker/apis/hevy_app/workouts.py`         | 16     |
| `fitness_tracker/database/services/tracker.py`      | 16     |
| `fitness_tracker/apis/true_coach/session.py`        | 15     |
| `fitness_tracker/apis/true_coach/auth.py`           | 14     |
| `fitness_tracker/database/repository/true_coach.py` | 14     |
| `fitness_tracker/apis/hevy_app/routines.py`         | 13     |
| `fitness_tracker/apis/true_coach/assessments.py`    | 10     |


### ruff_check


| File                                                | Issues |
| --------------------------------------------------- | ------ |
| `fitness_tracker/apis/true_coach/types.py`          | 55     |
| `fitness_tracker/apis/hevy_app/types.py`            | 44     |
| `fitness_tracker/database/repository/hevy_app.py`   | 39     |
| `fitness_tracker/database/services/true_coach.py`   | 35     |
| `fitness_tracker/database/services/hevy_app.py`     | 30     |
| `fitness_tracker/apis/true_coach/auth.py`           | 25     |
| `fitness_tracker/sync/hevy_tracker/sync.py`         | 24     |
| `fitness_tracker/apis/true_coach/session.py`        | 22     |
| `fitness_tracker/apis/hevy_app/session.py`          | 21     |
| `fitness_tracker/sync/apple_health_tracker/sync.py` | 19     |
| `fitness_tracker/apis/hevy_app/web_session.py`      | 18     |
| `fitness_tracker/apis/hevy_app/workouts.py`         | 18     |
| `fitness_tracker/llm/fitness_llm.py`                | 18     |
| `fitness_tracker/database/models/true_coach.py`     | 17     |
| `fitness_tracker/sync/tracker_hevy/utils.py`        | 17     |


### ruff_format


| File                                              | Issues |
| ------------------------------------------------- | ------ |
| `fitness_tracker/apis/__init__.py`                | 1      |
| `fitness_tracker/apis/hevy_app/__init__.py`       | 1      |
| `fitness_tracker/apis/hevy_app/exceptions.py`     | 1      |
| `fitness_tracker/apis/hevy_app/session.py`        | 1      |
| `fitness_tracker/apis/hevy_app/types.py`          | 1      |
| `fitness_tracker/apis/true_coach/__init__.py`     | 1      |
| `fitness_tracker/apis/true_coach/assessments.py`  | 1      |
| `fitness_tracker/apis/true_coach/auth.py`         | 1      |
| `fitness_tracker/apis/true_coach/client.py`       | 1      |
| `fitness_tracker/apis/true_coach/exceptions.py`   | 1      |
| `fitness_tracker/apis/true_coach/exercises.py`    | 1      |
| `fitness_tracker/apis/true_coach/session.py`      | 1      |
| `fitness_tracker/database/__init__.py`            | 1      |
| `fitness_tracker/database/models/__init__.py`     | 1      |
| `fitness_tracker/database/models/apple_health.py` | 1      |


### slop_detector


| File                              | Issues |
| --------------------------------- | ------ |
| `(slop-detector) utils.py`        | 4      |
| `(slop-detector) base.py`         | 2      |
| `(slop-detector) apple_health.py` | 1      |
| `(slop-detector) hevy_app.py`     | 1      |
| `(slop-detector) sync.py`         | 1      |
| `(slop-detector) tracker.py`      | 1      |
| `(slop-detector) true_coach.py`   | 1      |


### sloppylint


| File                                           | Issues |
| ---------------------------------------------- | ------ |
| `fitness_tracker/apis/true_coach/auth.py`      | 1      |
| `fitness_tracker/apis/true_coach/exercises.py` | 1      |
| `fitness_tracker/database/repository/base.py`  | 1      |
| `fitness_tracker/database/services/base.py`    | 1      |
| `fitness_tracker/sync/hevy_true_coach/sync.py` | 1      |


### ty


| File                                               | Issues |
| -------------------------------------------------- | ------ |
| `fitness_tracker/sync/tracker_hevy/sync.py`        | 10     |
| `fitness_tracker/sync/hevy_tracker/sync.py`        | 8      |
| `fitness_tracker/sync/true_coach_hevy/sync.py`     | 8      |
| `fitness_tracker/database/repository/base.py`      | 7      |
| `fitness_tracker/sync/tracker_true_coach/sync.py`  | 7      |
| `fitness_tracker/database/services/true_coach.py`  | 6      |
| `fitness_tracker/database/models/base.py`          | 5      |
| `fitness_tracker/sync/hevy_true_coach/utils.py`    | 5      |
| `fitness_tracker/sync/hevy_true_coach/sync.py`     | 4      |
| `fitness_tracker/sync/tracker_hevy/utils.py`       | 4      |
| `fitness_tracker/sync/tracker_true_coach/utils.py` | 4      |
| `fitness_tracker/sync/true_coach_hevy/utils.py`    | 4      |
| `fitness_tracker/llm/open_ai_llm.py`               | 3      |
| `fitness_tracker/apis/hevy_app/session.py`         | 2      |
| `fitness_tracker/apis/hevy_app/web_session.py`     | 2      |


