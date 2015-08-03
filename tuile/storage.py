import struct
import os
import json
from pathlib import Path

from six import BytesIO
from six.moves import range

from PIL import Image


class Index(object):
    def __init__(self, fh, size, entry_format):
        self.fh = fh
        self.cols, self.rows = size
        self.entry_format = entry_format
        self.entry_size = struct.calcsize(self.entry_format)

    @classmethod
    def new(cls, path, config):
        cols, rows = config['columns'], config['rows']
        entry_format = config['index_entry_format']
        entry_size = struct.calcsize(entry_format)
        index_size = cols * rows * entry_size
        index_fh = path.joinpath(config['index_filename']).open('w+b')
        index_fh.truncate(index_size)
        return cls(
            index_fh,
            (cols, rows),
            entry_format,
        )

    def get_entry(self, col, row):
        entry_offset = (row * self.cols + col) * self.entry_size
        self.fh.seek(entry_offset)
        return struct.unpack(self.entry_format, self.fh.read(self.entry_size))

    def set_entry(self, col, row, file_index, offset, size, flags=0):
        entry_offset = (row * self.cols + col) * self.entry_size
        self.fh.seek(entry_offset)
        entry = struct.pack(self.entry_format, file_index, offset, size, flags)
        self.fh.write(entry)

    @property
    def size(self):
        return self.cols, self.rows

    def __iter__(self):
        for row in range(self.rows):
            for col in range(self.cols):
                yield (col, row)

    def __len__(self):
        return self.rows * self.cols

    def itermask(self, mask):
        for coord in self:
            if self[coord][-1] & mask:
                yield coord

    def __getitem__(self, key):
        col, row = key
        return self.get_entry(col, row)

    def close(self):
        self.fh.close()


class MultiFileStorage(object):
    RO_MODE = 'rb'
    RW_MODE = 'r+b'
    CREATE_MODE = 'w+b'

    def __init__(self, path, max_file_size, filename_format):
        self.path = path
        self.files = []
        self.max_file_size = max_file_size
        self.filename_format = filename_format

        # Read in existing files
        while True:
            file_path = self.get_file_path()
            if not file_path.exists():
                break
            self.open(len(self.files), self.RO_MODE)

        if not self.files:
            # If no files exist, create a new one
            self.open(0, 'w+b')
        else:
            # Reopen the last file in rw mode
            self.open(len(self.files) - 1, self.RW_MODE)
            self.files[-1].seek(0, os.SEEK_END)

        self.current_write_offset = self.files[-1].tell()

    def __iter__(self):
        for col, row in self.index:
            yield self.get_tile_image(col, row)

    def open(self, index, mode):
        assert 0 <= index <= len(self.files)
        fh = self.get_file_path(index).open(mode)
        if index < len(self.files):
            self.files[index].close()
            self.files[index] = fh
        else:
            self.files.append(fh)
        return self.files[index]

    def write_chunk(self, chunk):
        assert isinstance(chunk, str)
        size = len(chunk)
        assert size < self.max_file_size
        if self.current_write_offset + size > self.max_file_size:
            self.open(len(self.files) - 1,  self.RO_MODE)
            self.open(len(self.files), self.CREATE_MODE)
            self.current_write_offset = 0

        self.files[-1].seek(self.current_write_offset)
        self.files[-1].write(chunk)

        offset = self.current_write_offset
        self.current_write_offset += size

        return len(self.files) - 1, offset, size

    def read_chunk(self, index, offset, size):
        fh = self.files[index]
        fh.seek(offset)
        return fh.read(size)

    def get_file_path(self, index=None):
        if index is None:
            index = len(self.files)
        filename = self.filename_format.format(index=index)
        return self.path.joinpath(filename)

    def close(self):
        for fh in self.files:
            fh.close()


class TilesStorage(object):
    INFO_FILENAME = 'info.json'
    INDEX_CLASS = Index
    STORAGE_CLASS = MultiFileStorage

    def __init__(self, index, storage):
        self.index = index
        self.storage = storage

    @classmethod
    def open(cls, path):
        path = Path(path)

        # TODO: Check version compatibility

        with path.joinpath(cls.INFO_FILENAME).open('rb') as fh:
            storage_config = json.load(fh)

        index_path = path.joinpath(storage_config['index_filename'])
        index = cls.INDEX_CLASS(
            index_path.open('r+b'),
            (storage_config['columns'], storage_config['rows']),
            storage_config['index_entry_format'],
        )

        storage = cls.STORAGE_CLASS(
            path,
            storage_config['max_tilesets_size'],
            storage_config['tilesets_filename_format'],
        )

        return cls(index, storage)

    @classmethod
    def new(cls, path, size):
        cols, rows = size

        # TODO: Select index format based on number of tiles

        storage_config = {
            'version': '1.0',
            'index_filename': 'index',
            'tilesets_filename_format': 'tiles{index:010d}',
            'max_tilesets_size': 1 * 1024 * 1024 * 1024 * 4,  # Given in bytes
            'columns': cols,
            'rows': rows,
            'index_entry_format': '>HQIB',  # index, offset, size, flags
        }

        # Create destination directory
        outdir = Path(path).with_suffix('.tuiles')
        assert not outdir.exists()
        outdir.mkdir()

        # Save configuration
        info_path = outdir.joinpath(TilesStorage.INFO_FILENAME)
        with info_path.open('wb') as fh:
            json.dump(storage_config, fh)

        index = cls.INDEX_CLASS.new(outdir, storage_config)
        storage = cls.STORAGE_CLASS(
            outdir,
            storage_config['max_tilesets_size'],
            storage_config['tilesets_filename_format'],
        )

        return cls(index, storage)

    @property
    def size(self):
        return self.index.size

    def get_tile(self, col, row):
        index, offset, size, flags = self.index[col, row]
        return self.storage.read_chunk(index, offset, size)

    def get_tile_image(self, col, row):
        tile_src = self.get_tile(col, row)
        return Image.open(BytesIO(tile_src))

    def set_tile(self, col, row, tile):
        tileset_index, offset, size = self.storage.write_chunk(tile)
        self.index.set_entry(col, row, tileset_index, offset, size)

    def close(self):
        self.storage.close()
        self.index.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
