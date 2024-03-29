from mcrcon import MCRcon
from pprint import pprint
from dotenv import load_dotenv
from datetime import datetime as dt

import os, json, csv, io, argparse, time

# ShowPlayersで不正なUIDの時に発行される
INVALID_PLAYER_UID = '00000000'

settings = {
    'rcon' : {
        # Palworld サーバIPアドレス
        'address': '127.0.0.1',
        # RCONポート(RCONPort)
        'port': 25575,
        # RCONパスワード(AdminPasswordと同じ)
        'password': ''
    },
    'time': {
        # プレイヤ情報の取得間隔
        'fetch_player_interval_sec': 30,
        # 自動でプレイヤキックを行うか
        'use_auto_player_kick': False,
        # ロード中にプレイヤキックを行うとサーバが無限ロードされるので安全よりに設定する方がよい
        'auto_kick_player_interval_sec': 3 * 60,
        # ループ間隔 変更不要
        'loop_interval_sec': 15
    },
    'data': {
        # ファイルパス
        'log_filepath': 'player_log.json',
        # セーブデータファイル名文字数 変更不要
        'save_filename_length': 32,
        # セーブファイル拡張子 変更不要
        'save_file_extension': 'sav'
    }
}

def init_setting():
    """引数から設定を初期化
    """

    # .env読み込み
    load_dotenv()

    parser = argparse.ArgumentParser(description="Outputs log of Palworld Server's connectee information")
    parser.add_argument('--address', help='Server address', default=os.getenv('SERVER_ADDRESS', '127.0.0.1'))
    parser.add_argument('--port', help='RCON port', default=os.getenv('RCON_PORT', 25575))
    parser.add_argument('--password', help='Admin password', default=os.getenv('RCON_PASSWORD',''))

    parser.add_argument('--fetch_player_interval_sec', help='RCON fetch player interval(sec)', default=os.getenv('FETCH_PLAYER_INTERVAL_SEC',30))
    parser.add_argument('--use_auto_player_kick', help='Use auto kick', default=os.getenv('USE_AUTO_KICK_PLAYER',False))
    parser.add_argument('--auto_kick_player_interval_sec', help='Auto kick interval(sec)', default=os.getenv('AUTO_KICK_PLAYER_INTERVAL_SEC',3 * 60))

    parser.add_argument('--log_filepath', help='Player log filepath', default=os.getenv('LOG_FILEPATH','player_log.json'))

    args = parser.parse_args()
    settings['rcon']['address'] = args.address
    settings['rcon']['port'] = int(args.port)
    settings['rcon']['password'] = args.password

    settings['time']['fetch_player_interval_sec'] = int(args.fetch_player_interval_sec)
    settings['time']['use_auto_player_kick'] = args.use_auto_player_kick == 'True'
    settings['time']['auto_kick_player_interval_sec'] = int(args.auto_kick_player_interval_sec)

    settings['data']['log_filepath'] = args.log_filepath

def import_players_json() -> dict:
    """ログを読み込み(過去のプレイヤ情報の復元)

    Returns:
        {
            steamid(string) : 
            {
                name: string, 
                playeruid: string,
                steamid: string,
                playeruid_hex: string,
                sav_filename: string
            }
        }: rcon showplayersから取得し整形された情報
    """
    if not os.path.isfile(settings['data']['log_filepath']):
        return {}

    with open(settings['data']['log_filepath'], 'r', encoding='utf-8') as f:
        player_log = json.load(f)
        pprint(player_log)
    
    return player_log

def export_players_json(player_log: dict):
    """ログを出力

    Args:
        player_log (
        {
            steamid(string) : 
            {
                name: string, 
                playeruid: string,
                steamid: string,
                playeruid_hex: string,
                sav_filename: string
            }
        }): プレイヤー情報
    """
    with open(settings['data']['log_filepath'], 'w', encoding='utf-8') as f:
        json.dump(player_log, f, ensure_ascii=False)

def fetch_players(rcon: MCRcon) -> dict:
    """接続集のユーザ情報wを取得

    Args:
        rcon (MCRcon): RCON

    Returns:
        player_log (
        {
            steamid(string) : 
            {
                name: string, 
                playeruid: string,
                steamid: string,
                playeruid_hex: string,
                sav_filename: string
            }
        }): 接続中のユーザ情報
    """
    players = {}
    for _ in range(3):
        try:
            res = rcon.command('ShowPlayers')
            reader = csv.reader(io.StringIO(res))
            
            # ヘッダ情報の読み取りを飛ばす
            next(reader)

            for row in reader:
                name = row[0]
                playeruid = row[1]
                steamid = row[2]

                is_invalid_playeruid = playeruid == INVALID_PLAYER_UID
                if is_invalid_playeruid:
                    print(f'Invalid user -> name: {name} staemid: {steamid} playeruid: {playeruid}')
                    continue
                
                playeruid_hex = format(int(playeruid), 'x')
                playeruid_hex_padded = playeruid_hex.ljust(settings['data']['save_filename_length'], '0')
                sav_filename = f"{playeruid_hex_padded}.{settings['data']['save_file_extension']}"

                players[steamid] = {
                    "name": name,
                    "playeruid": playeruid,
                    "steamid": steamid,
                    "playeruid_hex": playeruid_hex,
                    'sav_filename': sav_filename
                }

        except:
            rcon.connect()

    return players

def print_login_players(login_players: dict):
    """ログイン中のプレイヤを表示

    Args:
        login_players (dict): ログイン中のプレイヤ情報
    """
    
    player_count = len(login_players)
    print(f'-----login players({player_count})-----')
    for player in login_players.values():
        name = player['name']
        staemid = player['steamid']
        print(f'{name}({staemid})')

def extract_new_players(all_players: dict, login_players: dict):
    """新規プレイヤを抽出

    Args:
        all_players (dict): 過去に取得済みのプレイヤ情報
        login_players (dict): 現在ログイン中のプレイヤ情報
    """

    new_players = {}
    for steamid, value in login_players.items():
        old_player = steamid in all_players
        if old_player:
            continue

        new_players[steamid] = value

    return new_players

def merge_login_players(prev_players: dict, now_players: dict) -> dict:
    """ログイン中のユーザ情報をマージ(ログアウト済みは排除)

    Args:
        prev_players (dict): 前回ログインのユーザ
        {
            steamid(string): first login time(datetime)
        }

        now_players (dict): 今ログイン中のユーザ
        {
            steamid(string) : 
            {
                name: string, 
                playeruid: string,
                steamid: string,
                playeruid_hex: string,
                sav_filename: string
            }
        }

    Returns:
        dict: { "steamid": datetime 最初にログインした時間 }
    """
    now = dt.now()
    merged_login_players = {}
    for steamid in now_players.keys():
        exists_prev = steamid in prev_players
        if exists_prev:
            merged_login_players[steamid] = prev_players[steamid]
        else: 
            merged_login_players[steamid] = now

    return merged_login_players

def kick_players(rcon: MCRcon, merged_login_players: dict):
    """長時間ログインしているユーザをキック

    Args:
        merged_login_players (dict): ログイン中のユーザ
        {
            steamid(string): first login time(datetime)
        }
    """
    now = dt.now()
    for steamid, first_login_time in merged_login_players.items():
        is_over_login_time_length = (now - first_login_time).total_seconds() >= settings['time']['auto_kick_player_interval_sec']
        if not is_over_login_time_length:
            continue

        try:
            command = f'KickPlayer {steamid}'
            rcon.command(command)
            print(command)
        except:
            print(f'Faild kick command {steamid}({first_login_time})')

if __name__ == "__main__":
    print('----start logger-----')

    init_setting()

    prev_fetch_time = dt.now()

    with MCRcon(settings['rcon']['address'], settings['rcon']['password'], settings['rcon']['port']) as rcon:
        rcon.tlsmode
        print('-----rcon connect success-----')

        all_players = import_players_json()
        login_players = {}
        prev_login_players = {}
        while True:
            now = dt.now()
            need_fetch = (now - prev_fetch_time).total_seconds() >= settings['time']['fetch_player_interval_sec']
            if need_fetch:
                login_players = fetch_players(rcon)
                new_players = extract_new_players(all_players, login_players)
                all_players = {**all_players, **new_players}
                
                prev_fetch_time = now

                print_login_players(login_players)

                exists_new_player = len(new_players) > 0
                if exists_new_player:
                    export_players_json(all_players)

                use_auto_player_kick = settings['time']['use_auto_player_kick']
                if use_auto_player_kick:
                    merged_login_players = merge_login_players(prev_login_players, login_players)
                    kick_players(rcon, merged_login_players)

                    prev_login_players = merged_login_players

            time.sleep(settings['time']['loop_interval_sec'])