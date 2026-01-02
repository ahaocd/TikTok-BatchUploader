import argparse
import asyncio
from datetime import datetime
from os.path import exists
from pathlib import Path

from conf import BASE_DIR
from uploader.tk_uploader.main_chrome import tiktok_setup, TiktokVideo
from utils.files_times import get_title_and_hashtags


SOCIAL_MEDIA_TIKTOK = 'tiktok'


def get_supported_social_media():
    return [SOCIAL_MEDIA_TIKTOK]


def get_cli_action():
    return ['upload', 'login']


def parse_schedule(schedule_raw):
    if schedule_raw:
        return datetime.strptime(schedule_raw, '%Y-%m-%d %H:%M')
    return None


async def main():
    parser = argparse.ArgumentParser(description='Upload video to TikTok.')
    parser.add_argument('platform', choices=get_supported_social_media(), help='tiktok')
    parser.add_argument('account_name', type=str, help='Account name')
    subparsers = parser.add_subparsers(dest='action', help='Choose action', required=True)
    
    for action in get_cli_action():
        action_parser = subparsers.add_parser(action)
        if action == 'upload':
            action_parser.add_argument('video_file', help='Path to video file')
            action_parser.add_argument('-pt', '--publish_type', type=int, choices=[0, 1], default=0)
            action_parser.add_argument('-t', '--schedule', help='Schedule time: %Y-%m-%d %H:%M')
    
    args = parser.parse_args()
    
    if args.action == 'upload':
        if not exists(args.video_file):
            raise FileNotFoundError(f'Video not found: {args.video_file}')
        if args.publish_type == 1 and not args.schedule:
            parser.error('Schedule required for scheduled publishing')

    account_file = Path(BASE_DIR / 'cookies' / f'{args.platform}_{args.account_name}.json')
    account_file.parent.mkdir(exist_ok=True)

    if args.action == 'login':
        print(f'Logging in: {args.account_name}')
        await tiktok_setup(str(account_file), handle=True)
    elif args.action == 'upload':
        title, tags = get_title_and_hashtags(args.video_file)
        publish_date = 0 if args.publish_type == 0 else parse_schedule(args.schedule)
        
        await tiktok_setup(account_file, handle=True)
        app = TiktokVideo(title, args.video_file, tags, publish_date, account_file)
        await app.main()


if __name__ == '__main__':
    asyncio.run(main())
