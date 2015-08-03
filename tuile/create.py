import re
import sys
from pathlib import Path

from tuile import storage


TILE_FILENAME_REGEX = 'tile-(?P<row>\d+)x(?P<col>\d+).jpeg'
tile_filename_pattern = re.compile(TILE_FILENAME_REGEX)


def get_coords(path):
    match = tile_filename_pattern.match(path.name)
    tilespec = match.groupdict()
    return int(tilespec['col']), int(tilespec['row'])


def create(tiles_dir, out_path):
    cols, rows = 0, 0

    for tile in Path(tiles_dir).iterdir():
        col, row = get_coords(tile)
        cols = max(col, cols)
        rows = max(row, rows)

    cols += 1
    rows += 1

    with storage.TilesStorage.new(out_path, (cols, rows)) as writer:
        for tile in Path(tiles_dir).iterdir():
            col, row = get_coords(tile)
            with tile.open('rb') as fh:
                writer.set_tile(col, row, fh.read())


create(sys.argv[1], sys.argv[2])
