from datetime import time

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ScheduleEntry(BaseModel):
    """One working block, in clinic-local time. day_of_week: 0 = Monday ... 6 = Sunday."""

    day_of_week: int = Field(ge=0, le=6)
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def check_times(self) -> "ScheduleEntry":
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be before end_time")
        return self


class ScheduleEntryResponse(ScheduleEntry):
    model_config = ConfigDict(from_attributes=True)

    id: int


class WeeklyScheduleUpdate(BaseModel):
    """The full weekly schedule. It replaces whatever was there before."""

    entries: list[ScheduleEntry] = Field(max_length=50)

    @model_validator(mode="after")
    def check_no_overlaps(self) -> "WeeklyScheduleUpdate":
        entries_by_day: dict[int, list[ScheduleEntry]] = {}
        for entry in self.entries:
            entries_by_day.setdefault(entry.day_of_week, []).append(entry)

        for day_entries in entries_by_day.values():
            day_entries.sort(key=lambda entry: entry.start_time)
            for index in range(1, len(day_entries)):
                previous_entry = day_entries[index - 1]
                current_entry = day_entries[index]
                if current_entry.start_time < previous_entry.end_time:
                    raise ValueError("schedule entries on the same day must not overlap")
        return self
