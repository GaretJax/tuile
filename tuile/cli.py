import click
from pathlib import Path

from six import BytesIO

from PIL import Image

from tuile.storage import TilesStorage


CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])


@click.group(context_settings=CONTEXT_SETTINGS)
def main():
    pass


@main.command()
@click.option('-p', '--pretend/--no-pretend', default=False)
@click.argument('path', type=click.Path(exists=True))
def check(path, pretend):
    empty, invalid = 0, 0

    with TilesStorage.open(path) as ts:
        tot = len(ts.index)

        with click.progressbar(ts.index, width=0, show_eta=True, show_pos=True,
                               show_percent=True) as bar:
            for col, row in bar:
                try:
                    _, _, size, _ = ts.index.get_entry(col, row)
                    if size:
                        ts.get_tile_image(col, row).load()
                    else:
                        empty += 1
                except Exception as e:
                    click.echo(str(e))
                    invalid += 1
                    if not pretend:
                        ts.set_tile(col, row, '')

    click.echo('Found {} invalid tiles'.format(invalid))
    click.echo('Found {} empty tiles'.format(empty))
    click.echo('{} tiles ({:%}) are now empty'.format(
        invalid + empty, (invalid + empty) * 1.0 / tot))


@main.command()
@click.option('-c', '--check/--no-check', default=False)
@click.argument('path', type=click.Path(exists=True))
def rebuild(path, check):
    path = Path(path)
    tmp_path = path.with_name('tmp')
    with TilesStorage.open(path) as ts:
        with TilesStorage.new(tmp_path, ts.size) as new_ts:
            with click.progressbar(ts.index, width=0, show_eta=True,
                                   show_pos=True, show_percent=True) as bar:
                for col, row in bar:
                    _, _, size, _ = ts.index.get_entry(col, row)
                    if not size:
                        continue
                    tile = ts.get_tile(col, row)
                    if check:
                        try:
                            Image.open(BytesIO(tile)).load()
                        except:
                            continue
                    new_ts.set_tile(col, row, tile)
