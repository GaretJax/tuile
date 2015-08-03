import os
import sys

from pathlib import Path

from twisted.python import log
from twisted.web import server, resource, static
from twisted.internet import reactor
from twisted.python.compat import networkString

from . import storage


log.startLogging(sys.stdout)


class Tile(static.File):
    isLeaf = True

    type = 'image/jpeg'
    encoding = None

    def get_tile_path(self, request):
        id, z, row, col = request.postpath
        col, fmt = col.split('.', 1)
        row = int(row)
        col = int(col)
        z = int(z)
        z = 50000
        path = os.path.join(
            id,
            str(z),
            'tile-{:04d}x{:04d}.{}'.format(row, col, fmt),
        )
        return self.preauthChild(path)

    def render_GET(self, request):
        request.setHeader(b'accept-ranges', b'bytes')
        try:
            self._setContentHeaders(request)
            with self.get_tile_path(request).open() as fh:
                return fh.read()
        except:
            page = resource.NoResource(message='Not found')
            return page.render(request)

        # producer = self.makeProducer(request, fileForReading)
        # producer.start()
        # return server.NOT_DONE_YET


class TileStorageResource(resource.Resource):
    isLeaf = True

    def __init__(self, base):
        self.base = Path(base)
        self.files = {}

    def _set_content_headers(self, request):
        request.setHeader(b'content-type', networkString('image/jpeg'))

    def render_GET(self, request):
        request.setHeader(b'accept-ranges', b'bytes')
        self._set_content_headers(request)
        tile = self.get_tile(request)
        if tile:
            return tile
        else:
            page = resource.NoResource(message='Not found')
            return page.render(request)

    def get_tileset(self, id, z):
        k = (id, z)
        if k not in self.files:
            path = (self.base
                    .joinpath(str(id))
                    .joinpath(str(z))
                    .with_suffix('.tuiles'))
            if not path.exists():
                self.files[k] = None
            else:
                self.files[k] = storage.TilesStorage.open(path)
        return self.files[k]

    def get_tile(self, request):
        id, z, row, col = request.postpath
        col, fmt = col.split('.', 1)
        row = int(row)
        col = int(col)
        z = int(z)
        tileset = self.get_tileset(id, z)
        return tileset.get_tile(col, row) if tileset else None


site = server.Site(TileStorageResource('/Users/garetjax/Documents/maps'))
reactor.listenTCP(8080, site)
reactor.run()
