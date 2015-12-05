#!/usr/bin/env python
import datetime
import re
from getpass import getpass

import requests
from lxml import html

skeleton_headers = {
    'Accept': 'Accept: image/gif, image/jpeg, image/pjpeg, application/x-ms-application, application/xaml+xml, application/x-ms-xbap, */*',
    'Accept-Encoding': 'gzip, deflate',
    'Accept-Language': 'zh-Hans-CN, zh-Hans; q=0.5',
    'Connection': 'keep-alive',
    'User-Agent': 'Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.1; Trident/7.0)'  # 伪装成Windows 7 IE 11（兼容性视图）
}

LOGIN_URL = 'http://gzb.szsy.cn:3000/cas/login'
CARD_SYSTEM_LOGIN_URL = 'http://gzb.szsy.cn/card/'
CALENDAR_URL = 'http://gzb.szsy.cn/card/Restaurant/RestaurantUserMenu/RestaurantUserSelect.aspx'
MENU_URL = 'http://gzb.szsy.cn/card/Restaurant/RestaurantUserMenu/RestaurantUserMenu.aspx'

logined_skeleton_form = {
    '__EVENTARGUMENT': '',
    '__LASTFOCUS': ''
}

MEAL_NAME = ('早餐', '午餐', '晚餐')

opener = requests.Session()


def login_cas(username, password, cas_param=None):
    """
    教务系统使用CAS中央登陆，以是否存在跳转页面的特征判断登录是否成功，见reference.txt
    参数为用户名, 密码, 上次登录返回的[jsessionid, lt]
    若成功，返回None
    若失败，返回下次登陆需要的JSESSIONID和lt
    """
    if cas_param is None:
        # 据观察，只有在第一次访问，即Cookie中没有JSESSIONID时，页面中的地址才会带上JSESSIONID
        # 说真的，这步没啥必要。不过，尽量模拟得逼真点吧
        # 而lt是会变化的
        login_page = opener.get(LOGIN_URL, headers=skeleton_headers)
        jsessionid = re.search('jsessionid=(.*?)"', login_page.text).group(1)
        lt = re.search('name="lt" value="(.*?)"', login_page.text).group(1)
        login_post_url = LOGIN_URL + ';jsessionid=' + jsessionid
    else:
        jsessionid = cas_param[0]
        lt = cas_param[1]
        login_post_url = LOGIN_URL

    login_form = {
        'username': username,
        'password': password,
        'lt': lt,
        '_eventId': 'submit',
        'submit': '登录'
    }
    cas_login_headers = skeleton_headers.copy()
    cas_login_headers['Referer'] = LOGIN_URL
    auth = opener.post(login_post_url, login_form, headers=cas_login_headers)
    auth_status = '<SCRIPT LANGUAGE="JavaScript">' in auth.text

    if auth_status:
        return None
    else:
        # lt是会变化的
        lt = re.search('name="lt" value="(.*?)"', auth.text).group(1)
        return [jsessionid, lt]


def login_card_system():
    """登录“一卡通”系统，返回值为用户的姓名和卡中的余额"""
    card_login_headers = skeleton_headers.copy()
    card_login_headers['Referer'] = 'http://gzb.szsy.cn:4000/lcconsole/login!getSSOMessage.action'
    card_login = opener.get(CARD_SYSTEM_LOGIN_URL, headers=card_login_headers)
    order_welcome_page = card_login.text  # 此处会302到欢迎页
    name = re.search(r'<span id="LblUserName">当前用户：(.*?)<\/span>', order_welcome_page).group(1)
    balance = re.search(r'<span id="LblBalance">帐户余额：(.*?)元<\/span>', order_welcome_page).group(1)

    return name, balance


def get_viewstate(page):
    """从页面中得到VIEWSTATE"""
    viewstate = re.search(r'id="__VIEWSTATE" value="(.*?)"', page).group(1)
    return viewstate


def get_eventvalidation(page):
    """从页面中得到EVENTVALIDATION"""
    eventvalidation = re.search(r'id="__EVENTVALIDATION" value="(.*?)"', page).group(1)
    return eventvalidation


def get_default_calendar():
    """第一次访问选择日期的页面，返回选择日期的页面，VIEWSTATE，EVENTVALIDATION"""
    get_default_calendar_headers = skeleton_headers.copy()
    get_default_calendar_headers['Referer'] = 'http://gzb.szsy.cn/card/Default.aspx'
    calendar = opener.get(CALENDAR_URL, headers=get_default_calendar_headers)
    calendar_page = calendar.text
    viewstate = get_viewstate(calendar_page)
    eventvalidation = get_eventvalidation(calendar_page)

    return calendar_page, viewstate, eventvalidation


def parse_date_list(page):
    """用来解析选择日期的页面，得到可查询的日期的列表"""
    date_list = re.findall(r'href="RestaurantUserMenu\.aspx\?Date=(\d{4}-\d{1,2}-\d{1,2})"', page)

    return date_list


def parse_default_calendar(page):
    """解析第一次得到的选择日期的页面，返回日期列表，已查询的月份，可查询的年份"""
    selected_year = re.search(r'<option selected="selected" value="\d{4}">(\d{4})<\/option>', page).group(1)
    selected_month = re.search(r'<option selected="selected" value="\d{1,2}">(\d{1,2})月<\/option>', page).group(1)
    selectable_year = re.findall(r'value="(\d{4})"', page)
    date_list = parse_date_list(page)
    queried_month = [selected_year + '-' + selected_month]

    return date_list, queried_month, selectable_year


def query_calendar(year, month, viewstate, eventvalidation):
    """查询对应月份的菜单，返回值为选择日期的页面, VIEWSTATE, EVENTVALIDATION"""
    query_calendar_form = logined_skeleton_form.copy()
    query_calendar_form.update({
        '__EVENTTARGET': 'DrplstMonth1$DrplstControl',
        '__VIEWSTATE': viewstate,
        '__EVENTVALIDATION': eventvalidation,
        'DrplstYear1$DrplstControl': year,
        'DrplstMonth1$DrplstControl': month.lstrip('0')
    })
    query_calendar_headers = skeleton_headers.copy()
    query_calendar_headers['Referer'] = CALENDAR_URL
    post_calendar = opener.post(CALENDAR_URL, query_calendar_form, headers=query_calendar_headers)
    calendar_page = post_calendar.text
    viewstate = get_viewstate(calendar_page)
    eventvalidation = get_eventvalidation(calendar_page)

    return calendar_page, viewstate, eventvalidation


def get_menu(date):
    """获得给定日期的菜单，返回菜单的页面，VIEWSTATE和EVENTVALIDATION"""
    get_menu_headers = skeleton_headers.copy()
    get_menu_headers['Referer'] = CALENDAR_URL
    menu = opener.get(MENU_URL, params={'Date': date}, headers=get_menu_headers)

    # 我也是被逼的……如果不这么干，lxml提取出的列表里会有那串空白
    # 且看上去remove_blank_text不是这么用的
    menu_tidied = re.sub(r'\r\n {24}(?: {4})?', '', menu.text)
    menu_tidied = menu_tidied.replace('&nbsp;', ' ')  # 避免在Windows下出现编码问题，GBK中没有\xa0
    viewstate = get_viewstate(menu_tidied)
    eventvalidation = get_eventvalidation(menu_tidied)

    return menu_tidied, viewstate, eventvalidation


def get_do_not_order_list(page):
    """参数为菜单页，返回一个不订餐的餐次列表"""
    do_not_order_list = [int(x) for x in
                         re.findall(r'name="Repeater1\$ctl0(\d)\$CbkMealtimes" checked="checked"', page)]
    return do_not_order_list


def parse_menu(page):
    """
    解析菜单
    返回值为解析后的菜单, 当日的餐数, 每餐菜的道数,
    已订购的菜的份数, 已勾选“不订餐”的餐次列表
    """

    # 只有装着菜单的table是带"id"属性的
    menu_count = len(re.findall(r'id="Repeater1_GvReport_(\d)"', page))

    menu_tree = html.fromstring(page)
    course_count = [0 for x in range(0, menu_count)]  # course n. a part of a meal served at one time
    menu_parsed = {}
    for meal_order in range(0, menu_count):  # 这是个半闭半开的区间[a,b)，且GvReport是从0开始编号的，故不用+1
        # https://docs.python.org/3/library/stdtypes.html#str.format
        xpath_menu = '//table[@id="Repeater1_GvReport_{0}"]/tr/td//text()'.format(meal_order)
        menu_item = menu_tree.xpath(xpath_menu)

        # 由于Python中没有多维数组，而我嫌初始化一个"list of list of list"太麻烦了
        # 故使用一个字典，(餐次, 编号, 列数) = '原表格内容'
        row = 0
        column = 0
        for i, item in enumerate(menu_item):
            menu_parsed[meal_order, row, column] = item

            # 尽管没遇到过菜数不是9的情况，但还是别把它写死吧
            if (column == 0) and (item != ' '):
                course_count[meal_order] += 1

            column += 1
            if i % 9 == 8:
                column = 0
                row += 1

    return menu_parsed, menu_count, course_count


def get_course_amount(menu, menu_count, course_count):
    """参数为菜单字典，当日的餐数，每餐的道数。返回值为菜单中已订菜的数量的字典"""
    course_amount = {}
    for meal_order in range(0, menu_count):
        for course in range(0, course_count[meal_order]):
            # (餐次, 编号) = 数量
            course_amount[meal_order, course] = int(menu[meal_order, course, 7])

    return course_amount


def gen_menu_param(course_amount):
    """参数为course_amount这个dict，返回值为CALLBACKPARAM"""
    param_string = ''
    for k, v in course_amount.items():
        # {0}用于和自己拼在一起。{1[0]}为key中的第一个数，即meal_order，{1[1]}即course
        param_string = '{0}Repeater1_GvReport_{1[0]}_TxtNum_{1[1]}@{2}|'.format(
            param_string, k, v
        )

    return param_string


def submit_menu(date, course_amount, do_not_order_list, to_select, to_deselect, viewstate, eventvalidation):
    """
    参数为提交菜单的日期, 菜的数量,
    原页面已勾选“不订餐”的餐次, 要改变“不订餐”状态的餐次, 要“不订餐”的餐次, 要取消“不订餐的餐次,
    菜单页的VIEWSTATE和EVENTVALIDATION
    返回是否成功的Bool
    """
    submit_menu_form = logined_skeleton_form.copy()
    submit_menu_form.update({
        '__VIEWSTATE': viewstate,
        '__VIEWSTATEENCRYPTED': '',
        'DrplstRestaurantBasis1$DrplstControl': '4d05282b-b96f-4a3f-ba54-fc218266a524',
        '__EVENTVALIDATION': eventvalidation
    })
    submit_menu_headers = skeleton_headers.copy()
    submit_menu_headers['Referer'] = MENU_URL + '?Date=' + date

    # 用来模拟浏览器的做法，提交“不订餐”的变化
    # 要一个一个加，一个一个减
    if to_select + to_deselect:
        # 把原页面已勾选“不订餐”的放入表单
        for meal_order in do_not_order_list:
            box_id = 'Repeater1$ctl0{0}$CbkMealtimes'.format(meal_order)
            submit_menu_form[box_id] = 'on'

        for meal_order in to_select + to_deselect:
            box_id = 'Repeater1$ctl0{0}$CbkMealtimes'.format(meal_order)

            if meal_order in to_select:
                submit_menu_form[box_id] = 'on'
            elif meal_order in to_deselect:
                del submit_menu_form[box_id]

            submit_menu_form['__EVENTTARGET'] = box_id
            submit_do_not_order = opener.post(
                MENU_URL,
                submit_menu_form,
                params={'Date': date}
            )
            submit_return_page = submit_do_not_order.text

            # 提交后会返回新页面，又要改这些
            # Evil ASP.NET!
            viewstate = get_viewstate(submit_return_page)
            eventvalidation = get_eventvalidation(submit_return_page)
            submit_menu_form.update({
                '__VIEWSTATE': viewstate,
                '__EVENTVALIDATION': eventvalidation
            })

    # 提交菜单
    menu_param = gen_menu_param(course_amount)
    submit_menu_form.update({
        '__EVENTTARGET': '',
        '__CALLBACKID': '__Page',
        '__CALLBACKPARAM': menu_param
    })

    post_menu = opener.post(
        MENU_URL,
        submit_menu_form,
        params={'Date': date},
        headers=submit_menu_headers
    )
    status = '订餐成功！' in post_menu.text

    return status


def main():
    print('深圳实验学校高中部网上订餐系统CLI客户端')

    # 记录login_cas返回值。若登录失败，可以复用上次登录返回的页面中的lt
    auth_return = None
    while True:
        student_id = int(input('\n输完按Enter\n请输入学号：'))
        if len(str(student_id)) == 7:
            pass
        else:
            print('请输入长度为7位数字的学号')
            continue
        print('是的，你在输密码的时候不会出现*，输完按Enter即可')
        password = getpass('请输入密码：')

        print('正在进行中央登录')
        auth_return = login_cas(student_id, password, auth_return)

        if auth_return:  # 若登录失败，由于被重定向回登陆页，login_cas()会返回一个list
            print('登录失败，请检查学号和密码是否正确')
            continue
        else:
            break

    print('正在登录校卡系统')
    student_name, card_balance = login_card_system()
    print("\n欢迎，{0}".format(student_name))
    print("您的卡上还有", card_balance, "元")

    print('正在初始化日期列表')
    calendar_page, viewstate_calendar, eventvalidation_calendar = get_default_calendar()
    date_list_full, queried_month, selectable_year = parse_default_calendar(calendar_page)
    print('当前月份内，您可以选择以下日期')
    for date in date_list_full:
        date_object = datetime.datetime.strptime(date, '%Y-%m-%d')
        print('{0} 星期{1}'.format(date, date_object.isoweekday()))
    # 说的是“72小时”，实际上是把那一整天排除了，故+1
    print("理论上说，现在能够订到", datetime.timedelta(3 + 1) + datetime.date.today(), "及以后的餐")

    while True:
        # 检查日期
        print('要是想得到别的月份的菜单，输一个那个月的日期')
        date = input('格式为：年-月-日，如：2015-9-30\n请输入日期：')
        date_splited = date.split('-')
        # 统一宽度。这样就能够处理2015-9-3这种“格式错误”的日期了
        date = '{0}-{1}-{2}'.format(
            date_splited[0].zfill(4),
            date_splited[1].zfill(2),
            date_splited[2].zfill(2)
        )
        month = date_splited[0] + '-' + date_splited[1].lstrip('0')
        # 首先，确认它是个正确的日期
        date_object = datetime.datetime.strptime(date, '%Y-%m-%d')
        # 其次，确认输入的年份在可选的年份中
        if date_splited[0] in selectable_year:
            pass
        else:
            print('请输入在')
            for year in selectable_year:
                print(year)
            print('中的年份')
            continue

        if date in date_list_full:
            pass
        elif month in queried_month:
            print('请输入')
            for item in date_list_full:
                print(item)
            print('中的日期')
            continue
        else:  # 若输入的日期不存在，向服务器查询输入的月份
            print('正在获取对应月份的订餐日期列表')
            date_page, viewstate_calendar, eventvalidation_calendar = query_calendar(
                date_splited[0], date_splited[1],
                viewstate_calendar, eventvalidation_calendar
            )

            date_list_current = parse_date_list(date_page)
            date_list_full.extend(date_list_current)
            queried_month.append(month)

            if len(date_list_current) == 0:
                print('月份内没有可以点餐的日期')
                continue
            elif date in date_list_current:
                pass
            else:
                print('请输入')
                for date in date_list_full:
                    date_object = datetime.datetime.strptime(date, '%Y-%m-%d')
                    print('{0} 星期{1}'.format(date, date_object.isoweekday()))
                print('中的日期')
                continue

        # 拉菜单
        print('正在获取菜单')
        menu_page, viewstate_menu, eventvalidation_menu = get_menu(date)
        do_not_order_list = get_do_not_order_list(menu_page)
        menu, menu_count, course_count = parse_menu(menu_page)
        course_amount = get_course_amount(menu, menu_count, course_count)

        # 准备记录“不订餐”状态变化的餐次的列表
        to_select = []
        to_deselect = []

        print('{0}，星期{1}'.format(date, date_object.isoweekday()))
        for meal_order in range(0, menu_count):
            # 打印菜单
            print('\n{0}菜单'.format(MEAL_NAME[meal_order]))
            print('编号\t类别\t菜名\t\t单价\t最大份数\t订购份数\t订餐状态')
            for course in range(0, course_count[meal_order]):
                print('\t'.join([
                    menu[meal_order, course, 0],
                    menu[meal_order, course, 1],
                    menu[meal_order, course, 2],
                    menu[meal_order, course, 5],
                    menu[meal_order, course, 6],
                    menu[meal_order, course, 7],
                    menu[meal_order, course, 8]]
                ))

            if meal_order in do_not_order_list:
                print('\n此餐已被选上“不定餐”')
                do_not_order = True
            else:
                do_not_order = False

            # 修改菜单
            if menu[meal_order, course_count[meal_order], 3] == ' ':  # 参考reference.txt附上的两份菜单，just a dirty trick
                print('菜单无法更改')
                menu_mutable = False
                continue
            elif menu[meal_order, course_count[meal_order], 3] == '合计:':
                print('\n菜单可更改')  # 如果菜单是可以提交的，那么最后一行会少3列。一般每行有9列。故在此插入换行符，以取得 较统一的效果
                menu_mutable = True
                set_meal_selected = False
                # 用于记录必选菜的编号，以处理必选菜不在最后的特殊情况
                required_course = []

                order_status = input("请问您要定这一餐吗？输N不订餐，输其他字符继续").strip().capitalize()
                if 'N' in order_status:
                    # 由于浏览器的行为是在选中“不订餐”后立即向服务器发送状态变化的请求，而这么干有些浪费时间，故把这些留到最后提交
                    if not do_not_order:
                        to_select.append(meal_order)

                    # 用来占位，不然服务器不认
                    for course in range(0, course_count[meal_order]):
                        course_amount[meal_order, course] = 0
                    continue
                else:
                    # 与上文的那个判断一起，为提交作准备
                    if do_not_order:
                        to_deselect.append(meal_order)

                    print('若您不需要改变订购份数，直接按Enter即可')
                    for course in range(0, course_count[meal_order]):
                        print('\n编号：{0} 菜名：{1} 单价：{2} 最大份数：{3} 已定份数：{4}'.format(
                            menu[meal_order, course, 0],
                            menu[meal_order, course, 2],
                            menu[meal_order, course, 5],
                            menu[meal_order, course, 6],
                            menu[meal_order, course, 7]
                        ))
                        while not menu[meal_order, course, 4] == '必选':
                            course_num = input('请输入您要点的份数：')
                            # 如果直接敲Enter，就跳出循环，因为原始值已经在course_amount里了
                            if not course_num:
                                break
                            else:
                                course_num = int(course_num)
                                if 0 <= course_num <= int(menu[meal_order, course, 6]):
                                    course_amount[meal_order, course] = course_num  # 将份数放入字典
                                    # 订了套餐就不用特意去订必选菜了
                                    if course_num == 1 and menu[meal_order, course, 3] == '套餐':
                                        set_meal_selected = True
                                    break
                                else:
                                    print('请输入一个大于等于0且小于等于{0}的整数'.format(
                                        menu[meal_order, course, 6]))
                                    continue
                        if menu[meal_order, course, 4] == '必选':
                            required_course.append(course)

                    # 放入必选菜
                    # 我也不知道会不会有某一餐有多道必选菜，所以最好还是不要写死了
                    if set_meal_selected:
                        course_num = 0
                    else:
                        course_num = 1

                    for course in required_course:
                        course_amount[meal_order, course] = course_num

        if menu_mutable:
            print('正在提交菜单')
            post_status = submit_menu(
                date, course_amount,
                do_not_order_list, to_select, to_deselect,
                viewstate_menu, eventvalidation_menu)

            if post_status:
                print('\n订餐成功')
            else:
                print('\n订餐失败')


if __name__ == "__main__":
    main()
