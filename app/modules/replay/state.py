from dataclasses import asdict, dataclass


@dataclass
class Dock:
    docked: int
    held: int = 0
    capacity: int = 0
    version_line: int = 0

    @property
    def free(self):
        return self.capacity - self.docked

    def reseat(self):
        total = self.docked + self.held
        self.docked = min(self.capacity, total)
        self.held = total - self.docked

    def public(self):
        return {**asdict(self), 'free': self.free}


def attempt(dock, kind, road):
    if dock.capacity == 0:
        return 'STATION_CLOSED', road
    if kind == 'rent':
        if not dock.docked:
            return 'NO_BIKE', road
        dock.docked -= 1
        dock.reseat()
        return None, road + 1
    if dock.free == 0:
        return 'NO_DOCK', road
    if not road:
        return 'NO_ROAD_BIKE', road
    dock.docked += 1
    return None, road - 1
