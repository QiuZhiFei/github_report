import json
import datetime
from datetime import timedelta
import calendar
import requests
from pathlib import Path
import sys
import configparser

config = configparser.ConfigParser()
config.read('config.ini')

API_URL = config.get('Credentials', 'API_URL', fallback=None)
USER_NAME = config.get('Credentials', 'USER_NAME', fallback=None)
TOKEN = config.get('Credentials', 'TOKEN', fallback=None)

if not API_URL or not USER_NAME or not TOKEN:
    print(f'''
请在本地创建 config.ini，并写入

[Credentials]

# The GitHub API URL you are using，eg: https://api.github.com
API_URL=

# Your GitHub username
USER_NAME=

# Your GitHub Personal Access Token obtained from /settings/tokens, eg: https://github.com/settings/tokens
TOKEN=

          ''')
    sys.exit(1)

def get_commits(user_name, start_date, end_date, page=1, per_page=100):
    cache_filename = f".cache/requests/{user_name}_{start_date}_{end_date}_page{page}.json"
    cache_path = Path(cache_filename)
    if cache_path.exists():
        with open(cache_path, 'r') as cache_file:
            return json.load(cache_file)
    
    url = f"{API_URL}/search/commits?q=author:{user_name}+committer-date:{start_date}..{end_date}&sort=author-date&order=desc&page={page}&per_page={per_page}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": "token " + TOKEN
    }
    response = requests.get(url, headers=headers)
    data = response.json()

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, 'w') as cache_file:
        json.dump(data, cache_file)

    return data

def get_commits_by_date(user_name, start_date, end_date, force=False):
    start_datetime = datetime.datetime.strptime(start_date, "%Y-%m-%d")
    end_datetime = datetime.datetime.strptime(end_date, "%Y-%m-%d")
    
    current_month_start = start_datetime
    
    page = 1
    per_page = 100
    commits = []

    while current_month_start <= end_datetime:
        current_month_last_day = calendar.monthrange(current_month_start.year, current_month_start.month)[1]
        current_month_end = datetime.datetime(current_month_start.year, current_month_start.month, current_month_last_day)

        response = get_commits(
            user_name=user_name,
            start_date=current_month_start.strftime("%Y-%m-%d"),
            end_date=current_month_end.strftime("%Y-%m-%d"),
            page=page,
            per_page=per_page
        )

        items = response.get('items', [])
        if items:
            commits.extend(items)
            page += 1
        else:
            current_month_start = current_month_end + timedelta(days=1)
            page = 1

    return commits

def get_commit_created_at(commit):
    created_at = commit['commit']['committer']['date']
    if created_at:
        commit_datetime = datetime.datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%S.%f%z")
        return commit_datetime
    return None

def format_time_period(commit_datetime):
    if commit_datetime.hour < 6:
        period = "凌晨"
    elif commit_datetime.hour < 12:
        period = "上午"
    elif commit_datetime.hour < 18:
        period = "下午"
    else:
        period = "晚上"
    return f"{commit_datetime.month}月{commit_datetime.day}日 {period}{commit_datetime.hour}点{commit_datetime.minute}分"

def filter_latest_commit(commits):
    nearest_commit = None
    nearest_commit_datetime = None

    for commit in commits:
        commit_datetime = get_commit_created_at(commit)

        # 如果在6点以后，则与第二天的6点进行比较
        target_time = commit_datetime.replace(hour=6, minute=0, second=0, microsecond=0)
        if commit_datetime.time() > datetime.time(6, 0):
            target_time += datetime.timedelta(days=1)
        time_diff = abs((commit_datetime - target_time).total_seconds())
        
        nearest_diff = sys.float_info.max
        if nearest_commit:
            # 如果在6点以后，则与第二天的6点进行比较
            nearest_target_time = nearest_commit_datetime.replace(hour=6, minute=0, second=0, microsecond=0)
            if nearest_commit_datetime.time() > datetime.time(6, 0):
                nearest_target_time += datetime.timedelta(days=1)
            nearest_diff = abs((nearest_commit_datetime - nearest_target_time).total_seconds())     

        if time_diff < nearest_diff:
            nearest_commit = commit
            nearest_commit_datetime = commit_datetime

    return nearest_commit

def filter_earliest_commit(commits):
    nearest_commit = None
    nearest_commit_datetime = None

    for commit in commits:
        commit_datetime = get_commit_created_at(commit)
        
        # 6点之前的commit直接忽略
        if commit_datetime.time() < datetime.time(6, 0):
            continue
        
        target_time = commit_datetime.replace(hour=6, minute=0, second=0, microsecond=0)
        time_diff = abs((commit_datetime - target_time).total_seconds())
        
        nearest_diff = sys.float_info.max
        if nearest_commit:
            nearest_target_time = nearest_commit_datetime.replace(hour=6, minute=0, second=0, microsecond=0)
            nearest_diff = abs((nearest_commit_datetime - nearest_target_time).total_seconds())     

        if time_diff < nearest_diff:
            nearest_commit = commit
            nearest_commit_datetime = commit_datetime

    return nearest_commit

def filter_monthly_commits(commits):
    commits_by_month = {}

    for commit in commits:
        commit_datetime = get_commit_created_at(commit)
        month_key = commit_datetime.month

        # 如果该月份尚未在 commits_by_month 中创建，则初始化为一个空列表
        if month_key not in commits_by_month:
            commits_by_month[month_key] = []

        # 将 commit 添加到对应月份的列表中
        commits_by_month[month_key].append(commit)

    return commits_by_month

def filter_commits_by_day(commits):
    commits_by_day = {}

    for commit in commits:
        commit_datetime = get_commit_created_at(commit)
        day_key = commit_datetime.date()

        # 如果该日期尚未在 commits_by_day 中创建，则初始化为一个空列表
        if day_key not in commits_by_day:
            commits_by_day[day_key] = []

        # 将 commit 添加到对应日期的列表中
        commits_by_day[day_key].append(commit)

    return commits_by_day

def filter_all_repos(commits):
    all_repos = set()

    for commit in commits:
        repo_name = commit['repository']['full_name']
        all_repos.add(repo_name)

    return all_repos

# 加载时间范围内的数据
commits = get_commits_by_date(USER_NAME, '2023-01-01', '2023-12-31')

# 过滤出 所有的仓库
all_repos = filter_all_repos(commits)

# 过滤出 每个月的提交
monthly_commits = filter_monthly_commits(commits)
max_month = max(monthly_commits, key=lambda k: len(monthly_commits[k]))

# 过滤出 每天的提交
day_commits = filter_commits_by_day(commits)
max_day = max(day_commits, key=lambda k: len(day_commits[k]))

# 过滤出 最晚的提交
latest_commit = filter_latest_commit(commits)

# 过滤出 最早的提交
earliest_commit = filter_earliest_commit(commits)

print(f'''
hi, {USER_NAME}

2023 年的每一次 GitHub 提交都非常值得我们去纪念

今年你共提交 {len(commits)} 次，分别流向 {len(all_repos)} 个仓库

{max_month}月的你格外忙碌，共有 {len(monthly_commits[max_month])} 个提交

{max_day.strftime("%Y年%m月%d日")}，这天的你活力十足，提交高达 {len(day_commits[max_day])} 次

全年最早一次提交，发布于 {format_time_period(get_commit_created_at(earliest_commit))}

全年最晚一次提交, 发布于 {format_time_period(get_commit_created_at(latest_commit))}
      ''')