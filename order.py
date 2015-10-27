#!/usr/bin/env python
from urllib import parse, request
from http import cookiejar
import re
import datetime
from lxml import etree, html

def tidy_date_list(tree):   
    raw_date_list = tree.xpath('//a[@target="RestaurantContent"]/@href')

    i = 0
    for item in raw_date_list:
        raw_date_list[i] = item.replace('RestaurantUserMenu.aspx?Date=', '')
        i += 1
    return raw_date_list

print('深圳实验学校高中部网上订餐系统CLI客户端')
cookie = cookiejar.CookieJar()
opener = request.build_opener(request.HTTPCookieProcessor(cookie))
headers = {
    'User-Agent': 'Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.1; Trident/7.0)'  # 伪装成Windows 7 IE 11（兼容性视图）
}

login_page_url = 'http://gzb.szsy.cn:3000/cas/login'
login_post_url = 'http://gzb.szsy.cn:3000/cas/login;jsessionid={0}'  # Skeleton
order_login_url = 'http://gzb.szsy.cn/card/'
select_date_url = 'http://gzb.szsy.cn/card/Restaurant/RestaurantUserMenu/RestaurantUserSelect.aspx'
menu_page_url = 'http://gzb.szsy.cn/card/Restaurant/RestaurantUserMenu/RestaurantUserMenu.aspx?Date={0}'  # Skeleton

# 获得JSESSIONID
login_page_request = request.Request(login_page_url, None, headers)
print('正在初始化')
login_page = opener.open(login_page_request)
evil_jsessionid = re.search(r'jsessionid=(.*?)"', login_page.read().decode('utf-8')).group(1)
login_post_url = login_post_url.format(evil_jsessionid)
# https://docs.python.org/3/library/stdtypes.html#str.format
# 说真的，上面那步没啥必要。不过，尽量模拟得逼真点吧

while True:
    student_id = int(input('\n请输入学号：'))
    if (len(str(student_id)) == 7):
        pass
    else:
        print('请输入长度为7位数字的学号')
        continue
    password = input('请输入密码：')

    login_form = {
        'username': student_id,
        'password': password,
        'lt': 'e1s1',
        '_eventId': 'submit',
        'submit': '登陆'
    }

    print('正在登录')
    # 登录（SSO）
    headers.update({'Referer': login_page_url})  # 添加Referer
    login_post_form = parse.urlencode(login_form).encode('utf-8')
    auth_request = request.Request(login_post_url, login_post_form, headers)
    auth = opener.open(auth_request)

    # 以是否存在跳转页面的特征判断登录是否成功
    auth_page = auth.read().decode('utf-8')
    auth_status = re.match('<SCRIPT LANGUAGE="JavaScript">', auth_page)

    if auth_status == None:  # 若登录失败，由于被重定向回登陆页，上面正则会返回None
        print('登录失败，请检查学号和密码是否正确')
        continue
    else:
        break

# 登录校卡系统
headers['Referer'] = 'http://gzb.szsy.cn:4000/lcconsole/login!getSSOMessage.action'  # 更新Referer
order_login_request = request.Request(order_login_url, None, headers)
order_login = opener.open(order_login_request)
order_welcome_page = order_login.read().decode('utf-8')  # 此处会302到欢迎页
student_name = re.search(r'<span id="LblUserName">当前用户：(.*?)<\/span>', order_welcome_page).group(1)
# 我觉得为了一个只用一次的页面开一棵DOM Tree太浪费了，用正则省事
print("欢迎，{0}".format(student_name))
print("理论上说，现在能够订到", datetime.timedelta(3 + 1) + datetime.date.today(), "及以后的餐")
# 说的是“72小时”，实际上是把那一整天排除了，故+1

while True:
    # 检查日期
    date = input('\n请输入日期（格式如：2015-09-30）：')
    date_splited = date.split('-')
    # 统一宽度。这样就能够处理2015-9-3这种“格式错误”的日期了
    date = '{0}-{1}-{2}'.format(date_splited[0].zfill(4), date_splited[1].zfill(2), date_splited[2].zfill(2))
    date_object = datetime.datetime(int(date_splited[0]), int(date_splited[1]), int(date_splited[2]))  # 首先，确认它是个正确的日期

    # 第一次访问选择日期的页面，若输入的日期存在，便去打印菜单。
    headers['Referer'] = 'http://gzb.szsy.cn/card/Default.aspx'  # 更新Referer
    check_date_first_request = request.Request(select_date_url, None, headers)
    print('正在检查日期 Stage1')
    check_date_first = opener.open(check_date_first_request)
    date_tree = html.fromstring(check_date_first.read().decode('utf-8'))

    date_list = tidy_date_list(date_tree)

    if date in date_list:
        pass
    else:  # 若输入的日期不存在，向服务器查询输入的月份
        evil_viewstate = date_tree.xpath('//*[@id="__VIEWSTATE"]/@value')[0]
        evil_eventvalidation = date_tree.xpath('//*[@id="__EVENTVALIDATION"]/@value')[0]
        # They are evil, aren't they?

        # 制作获取对应月份页面的表单
        check_date_second_form = {
            '__EVENTTARGET': 'DrplstMonth1$DrplstControl',
            '__EVENTARGUMENT': '',
            '__LASTFOCUS': '',
            '__VIEWSTATE': evil_viewstate,
            '__EVENTVALIDATION': evil_eventvalidation,
            'DrplstYear1$DrplstControl': date_splited[0],
            'DrplstMonth1$DrplstControl': int(date_splited[1])  # 用途：将09变成9
        }

        headers['Referer'] = select_date_url  # 更新Referer
        check_date_second_post_form = parse.urlencode(check_date_second_form).encode('utf-8')
        check_date_second_request = request.Request(select_date_url, check_date_second_post_form, headers)
        print('正在检查日期 Stage2')
        check_date_second = opener.open(check_date_second_request)
        date_tree = html.fromstring(check_date_second.read().decode('utf-8'))
        date_item = date_tree.xpath('//a[@target="RestaurantContent"]/@href')

        date_list = tidy_date_list(date_tree)

        if len(date_list) == 0:
            print('月份内没有可以点餐的日期')
            continue
        elif date in date_list:
            pass
        else:
            print('请输入')
            for item in date_list:
                print(item)
            print('中的日期')
            continue

    # 拉菜单
    menu_page_url = menu_page_url.format(date)
    menu_request = request.Request(menu_page_url, None, headers)
    print('正在获取菜单')
    menu = opener.open(menu_request)

    # 我也是被逼的……如果不这么干，lxml提取出的列表里会有那串空白，且还不能用lxml.html.clean去掉
    # 看起来lxml不会自动去掉空格
    menu_tidied = re.sub(r'\r\n {24}( {4})?', '', menu.read().decode('utf-8'))
    menu_tidied = menu_tidied.replace('&nbsp;', ' ')  # 避免在Windows下出现问题，GBK中没有\xa0
    menu_tree = html.fromstring(menu_tidied)

    # 没办法，不同页面的这两个值都不一样
    evil_viewstate = menu_tree.xpath('//*[@id="__VIEWSTATE"]/@value')[0]
    evil_eventvalidation = menu_tree.xpath('//*[@id="__EVENTVALIDATION"]/@value')[0]

    menu_count = len(menu_tree.xpath('//table[@id]'))  # 只有装着菜单的table是带"id"属性的
    menu_parsed = {}  # 由于Python中没有多维数组，而我嫌初始化一个"list of list of list"太麻烦，故使用一个字典，(餐次, 编号, 列数) = '原表格内容'
    course_amount = {}  # (餐次, 编号) = 数量
    callbackparam = ''  # 用于提交的菜单参数

    print('{0}，星期{1}'.format(date, date_object.isoweekday()))
    for meal_order in range(0, menu_count):  # 这是个半闭半开的区间[a,b)，且GvReport是从0开始编号的，故这样
        xpath_exp = '//table[@id="Repeater1_GvReport_{0}"]/tr/td//text()'.format(meal_order)
        menu_item = menu_tree.xpath(xpath_exp)

        # 打印菜单
        meal_order_dict = {
            0: '早餐菜单',
            1: '午餐菜单',
            2: '晚餐菜单'
        }
        print('\n{0}'.format(meal_order_dict[meal_order]))
        print('编号\t类别\t菜名\t\t套餐\t必选\t单价\t最大份数\t订购份数\t订餐状态')
        row = 0
        column = 0
        i = 0
        for item in menu_item:
            print(item, end='\t')  # 这样就不会换行了，以制表符分隔元素
            menu_parsed[meal_order, row, column] = item

            if column == 4:
                if item == '必选':
                    required_course = row  # 用于记录必选菜的编号，以处理必选菜不在最后的特殊情况

            i += 1
            column += 1
            if (i % 9 == 0):
                column = 0
                row += 1
                print()  # 换行打印

        # 修改菜单
        if (menu_parsed[meal_order, 9, 3] == ' '):  # 参考reference.txt附上的两份菜单，just a dirty trick
            print('菜单无法更改')
            menu_mutable = False
            continue
        elif (menu_parsed[meal_order, 9, 3] == '合计:'):
            print('\n菜单可更改')  # 如果菜单是可以提交的，那么最后一行会少3列。一般每行有9列。故在此插入换行符，以取得较统一的效果
            menu_mutable = True
            for course in range(0, 8+1):  # course n. a part of a meal served at one time
                print('\n编号：{0} 菜名：{1} 单价：{2} 最大份数：{3}'.format(
                    menu_parsed[meal_order, course, 0],
                    menu_parsed[meal_order, course, 2],
                    menu_parsed[meal_order, course, 5],
                    menu_parsed[meal_order, course, 6]))
                while course != required_course:
                    course_num = int(input('请输入您要点的份数：'))
                    if (0 <= course_num <= int(menu_parsed[meal_order, course, 6])):
                        course_amount[meal_order, course] = course_num  # 将份数放入字典
                        break
                    else:
                        print('请输入一个大于等于0且小于等于{0}的整数'.format(
                            menu_parsed[meal_order, course, 6]))
                        continue
                course_amount[meal_order, required_course] = 1  # 放入必选菜

            for course in range(0, 8+1):
                callbackparam = '{0}Repeater1_GvReport_{1}_TxtNum_{2}@{3}|'.format(
                    callbackparam,  # 拼起来
                    meal_order,
                    course,
                    course_amount[meal_order, course])

    # 想不出别的用来处理不可修改的菜单的方法，只好声明一个menu_mutable了
    if menu_mutable:
        # 制作用于提交的表单
        menu_form = {
            '__EVENTTARGET': '',
            '__EVENTARGUMENT': '',
            '__LASTFOCUS': '',
            '__VIEWSTATE': evil_viewstate,
            '__VIEWSTATEENCRYPTED': '',
            'DrplstRestaurantBasis1$DrplstControl': '4d05282b-b96f-4a3f-ba54-fc218266a524',  # 页面上“选择餐厅”的值
            '__CALLBACKID': '__Page',
            '__CALLBACKPARAM': callbackparam,
            '__EVENTVALIDATION': evil_eventvalidation
        }
        post_menu_form = parse.urlencode(menu_form).encode('utf-8')
        headers['Referer'] = menu_page_url  # 更新Referer，拉菜单前已经拼好了
        submit_menu_request = request.Request(menu_page_url, post_menu_form, headers)
        print('\n正在提交菜单')
        submit_menu = opener.open(submit_menu_request)

        if '订餐成功！' in submit_menu.read().decode('utf-8'):
            print('\n订餐成功')
        else:
            print('\n订餐失败')

    menu_page_url = 'http://gzb.szsy.cn/card/Restaurant/RestaurantUserMenu/RestaurantUserMenu.aspx?Date={0}'  # 重新赋值
