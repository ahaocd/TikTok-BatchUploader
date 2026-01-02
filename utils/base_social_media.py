from pathlib import Path

try:
    from conf import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).parent.parent.resolve()

SOCIAL_MEDIA_TIKTOK = 'tiktok'


def get_supported_social_media():
    return [SOCIAL_MEDIA_TIKTOK]


def get_cli_action():
    return ['upload', 'login']


async def set_init_script(context):
    stealth_js_path = Path(BASE_DIR / 'utils/stealth.min.js')
    await context.add_init_script(path=stealth_js_path)
