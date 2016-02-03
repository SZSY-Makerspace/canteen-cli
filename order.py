#!/usr/bin/env python
import datetime
import re
from getpass import getpass

import requests
from lxml import html

skeleton_headers = {
    'Accept': 'image/gif, image/jpeg, image/pjpeg, application/x-ms-application, application/xaml+xml, \
application/x-ms-xbap, */*',
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

session = requests.Session()


class SessionExpired(Exception):
    def __str__(self):
        return "Your session has expired."


def get(url, params=None, headers=skeleton_headers):
    real_headers = skeleton_headers.copy()
    real_headers.update(headers)
    request = session.get(url, params=params, headers=real_headers)

    if LOGIN_URL in request.url:
        raise SessionExpired
    return request


def post(url, data, params=None, headers=skeleton_headers):
    real_headers = skeleton_headers.copy()
    real_headers.update(headers)
    real_data = logined_skeleton_form.copy()
    real_data.update(data)
    request = session.post(url, real_data, params=params, headers=real_headers)

    if LOGIN_URL in request.url:
        raise SessionExpired
    return request


def login_cas(username, password, cas_param=None):
    """
    教务系统使用CAS中央登陆，以是否存在跳转页面的特征判断登录是否成功，见reference.txt
    若成功，返回None
    若失败，返回下次登陆需要的JSESSIONID和lt
    :type username: str
    :type password: str
    :type cas_param: list
    :param username: 用户名
    :param password: 密码
    :param cas_param: 上次登录返回的[jsessionid, lt]
    """
    if cas_param is None:
        # 据观察，只有在第一次访问，即Cookie中没有JSESSIONID时，页面中的地址才会带上JSESSIONID
        # 说真的，这步没啥必要。不过，尽量模拟得逼真点吧
        # 而lt是会变化的
        login_page = session.get(LOGIN_URL, headers=skeleton_headers)
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
    auth = session.post(login_post_url, login_form, headers=cas_login_headers)
    auth_status = '<SCRIPT LANGUAGE="JavaScript">' in auth.text

    if auth_status:
        return None
    else:
        # lt是会变化的
        lt = re.search('name="lt" value="(.*?)"', auth.text).group(1)
        return [jsessionid, lt]


def login_card_system():
    """登录“一卡通”系统，返回值为用户的姓名和卡中的余额"""
    card_login_headers = {'Referer': 'http://gzb.szsy.cn:4000/lcconsole/login!getSSOMessage.action'}
    card_login = get(CARD_SYSTEM_LOGIN_URL, headers=card_login_headers)
    order_welcome_page = card_login.text  # 此处会302到欢迎页
    name = re.search(r'<span id="LblUserName">当前用户：(.*?)</span>', order_welcome_page).group(1)
    balance = re.search(r'<span id="LblBalance">帐户余额：(.*?)元</span>', order_welcome_page).group(1)

    return name, balance


def get_web_forms_field(page):
    """
    从页面中得到ASP.NET Web Forms的View State, View State Generator, Event Validation
    [viewstate, viewstategenertor, eventvalidation]
    :type page: str
    :rtype: list
    """
    vs = re.search(r'id="__VIEWSTATE" value="(.*?)"', page).group(1)
    vsg = re.search(r'id="__VIEWSTATEGENERATOR" value="(.*?)"', page).group(1)
    ev = re.search(r'id="__EVENTVALIDATION" value="(.*?)"', page).group(1)
    return [vs, vsg, ev]


def parse_date_list(page):
    """
    用来解析选择日期的页面，得到可查询的日期的列表
    :type page: str
    :rtype: list
    """
    date_list = re.findall(r'\?Date=(\d{4}-\d{2}-\d{2})', page)

    return date_list


class Calendar(dict):
    def __init__(self, selected_year, form_param, selectable_year, init_dict):
        super().__init__()
        # 0-成功, 1-年份不可选
        self.status = 0
        self.selected_year = selected_year
        self.form_param = form_param

        self.selectable_year = selectable_year

        self.update(init_dict)

    @classmethod
    def calendar_init(cls):
        """第一次访问选择日期的页面，返回选择日期的页面，VIEWSTATE，EVENTVALIDATION"""
        get_default_calendar_headers = {'Referer': 'http://gzb.szsy.cn/card/Default.aspx'}
        calendar = get(CALENDAR_URL, headers=get_default_calendar_headers)
        page = calendar.text
        form_param = get_web_forms_field(page)
        selectable_year = [int(year) for year in re.findall(r'value="(\d{4})"', page)]
        selected_year = re.search(r'<option selected="selected" value="\d{4}">(\d{4})</option>', page).group(1)
        selected_month = re.search(r'<option selected="selected" value="\d{1,2}">(\d{1,2})月</option>', page).group(
            1).zfill(2)
        date_string = selected_year + '-' + selected_month
        init_dict = {date_string: parse_date_list(page)}
        return cls(int(selected_year), form_param, selectable_year, init_dict)

    def test(self, date):
        """
        :type date: datetime.date
        """
        if date.year in self.selectable_year:
            query_string = date.strftime('%Y-%m')
            date_string = date.strftime('%Y-%m-%d')
            if query_string in self:
                pass
            else:
                self[query_string] = self.query_calendar(date.year, date.month)
            return date_string in self[query_string]
        else:
            return False

    def query_calendar(self, year, month):
        """
        查询对应月份的菜单
        :type year: int
        :type month: int
        :param year: 菜单的年份
        :param month: 菜单的月份
        """
        query_calendar_form = {
            '__EVENTTARGET': 'DrplstMonth1$DrplstControl',
            '__VIEWSTATE': self.form_param[0],
            '__VIEWSTATEGENERATOR': self.form_param[1],
            '__EVENTVALIDATION': self.form_param[2],
            'DrplstYear1$DrplstControl': year,
            'DrplstMonth1$DrplstControl': month
        }
        query_calendar_headers = {'Referer': CALENDAR_URL}
        post_calendar = post(CALENDAR_URL, query_calendar_form, headers=query_calendar_headers)
        page = post_calendar.text
        self.form_param = get_web_forms_field(page)

        if not year == self.selected_year:
            # 切换年份时，需要像处理不订餐那么搞
            query_calendar_form.update({
                '__VIEWSTATE': self.form_param[0],
                '__VIEWSTATEGENERATOR': self.form_param[1],
                '__EVENTVALIDATION': self.form_param[2]
            })
            post_calendar = post(CALENDAR_URL, query_calendar_form, headers=query_calendar_headers)
            page = post_calendar.text
            self.form_param = get_web_forms_field(page)
            self.selected_year = year

        return parse_date_list(page)


def get_course_count(page, menu_sequence):
    """
    :type page: str
    :type menu_sequence: int
    :param menu_sequence: 这一餐的序号
    :rtype: int
    """
    return len(re.findall(r'Repeater1_GvReport_{0}_LblMaxno_\d'.format(menu_sequence), page))


class Course(object):
    def __init__(self, seq, course):
        self.id = seq
        self.num = int(course[0])
        self.type = course[1]
        self.name = course[2]
        self.price = float(course[5])
        self.max = int(course[6])
        self.current = int(course[7])


class Meal(list):
    def __init__(self, seq, menu_list, course_count):
        super().__init__()
        self.required_course = []
        self.id = seq

        for course_seq in range(course_count):
            start = 9 * course_seq
            end = 9 * (course_seq + 1)
            l = menu_list[start:end]
            # 用于记录必选菜的编号，以处理必选菜不在最后的特殊情况
            if l[4] == '必选':
                self.required_course.append(course_seq)
            self.append(Course(course_seq, l))


class Menu(list):
    def __init__(self, date):
        super().__init__()
        page = self.get_menu(date)
        self.form_param = get_web_forms_field(page)
        # 只有装着菜单的table是带"id"属性的
        meal_count = len(re.findall(r'id="Repeater1_GvReport_(\d)"', page))
        self.do_not_order = [int(x) for x in
                             re.findall(r'name="Repeater1\$ctl0(\d)\$CbkMealtimes" checked="checked"', page)]

        if '<a onclick="return subs();"' in page:
            self.mutable = True
        elif '<a onclick="return msg();"' in page:
            self.mutable = False

        tree = html.fromstring(page)
        for meal_seq in range(meal_count):
            # 尽管没遇到过菜数不是9的情况，但还是别把它写死吧
            course_count = get_course_count(page, meal_seq)
            # 若菜单不可修改，总价那一行不会有那个id标签
            if not self.mutable:
                course_count -= 1
            xpath = '//table[@id="Repeater1_GvReport_{0}"]/tr/td//text()'.format(meal_seq)
            menu_item = tree.xpath(xpath)
            self.append(Meal(meal_seq, menu_item, course_count))

    @staticmethod
    def get_menu(date):
        """
        获得给定日期的菜单，返回菜单的页面
        :type date: str
        :rtype: str
        """
        get_menu_headers = {'Referer': CALENDAR_URL}
        menu = get(MENU_URL, params={'Date': date}, headers=get_menu_headers)

        # 我也是被逼的……如果不这么干，lxml提取出的列表里会有那串空白
        # 且看上去remove_blank_text不是这么用的
        page = re.sub(r'\r\n {24}(?: {4})?', '', menu.text)
        page = page.replace('&nbsp;', ' ')  # 避免在Windows下出现编码问题，GBK中没有\xa0
        return page

    def get_course_amount(self):
        """
        参数为菜单。返回值为菜单中已订菜的数量的字典
        :rtype: dict
        """
        course_amount = {}
        for meal in self:
            for course in meal:
                # (餐次, 编号) = 数量
                course_amount[meal.id, course.id] = course.current

        return course_amount


def gen_menu_param(course_amount):
    """
    参数为course_amount这个dict，返回值为CALLBACKPARAM
    :type course_amount: dict
    :rtype: str
    """
    param_string = ''
    for k, v in course_amount.items():
        # {0}用于和自己拼在一起。{1[0]}为key中的第一个数，即meal_order，{1[1]}即course
        param_string = '{0}Repeater1_GvReport_{1[0]}_TxtNum_{1[1]}@{2}|'.format(
            param_string, k, v
        )

    return param_string


def submit_menu(date, course_amount, do_not_order, form_param):
    """
    返回是否成功的Bool
    :type date: str
    :type course_amount: dict
    :type do_not_order: list
    :type form_param: list
    :param date: 提交菜单的日期
    :param course_amount: 菜的数量
    :param do_not_order: [原页面已勾选“不订餐”的餐次, 要“不订餐”的餐次, 要取消“不订餐”的餐次]
    :param form_param: 菜单页与ASP.NET Web Forms相关的字段
    :rtype: bool
    """
    # unpack
    do_not_order_list, to_select, to_deselect = do_not_order
    submit_menu_form = {
        '__VIEWSTATE': form_param[0],
        '__VIEWSTATEGENERATOR': form_param[1],
        '__VIEWSTATEENCRYPTED': '',
        'DrplstRestaurantBasis1$DrplstControl': '4d05282b-b96f-4a3f-ba54-fc218266a524',
        '__EVENTVALIDATION': form_param[2]
    }
    submit_menu_headers = {'Referer': MENU_URL + '?Date=' + date}

    # 把原页面已勾选“不订餐”的放入表单
    for meal_order in do_not_order_list:
        box_id = 'Repeater1$ctl0{0}$CbkMealtimes'.format(meal_order)
        submit_menu_form[box_id] = 'on'

    # 用来模拟浏览器的做法，提交“不订餐”的变化
    # 要一个一个加，一个一个减
    if to_select + to_deselect:
        for meal_order in to_select + to_deselect:
            box_id = 'Repeater1$ctl0{0}$CbkMealtimes'.format(meal_order)

            if meal_order in to_select:
                submit_menu_form[box_id] = 'on'
            elif meal_order in to_deselect:
                del submit_menu_form[box_id]

            submit_menu_form['__EVENTTARGET'] = box_id
            submit_do_not_order = post(
                MENU_URL,
                submit_menu_form,
                params={'Date': date},
                headers=submit_menu_headers
            )
            submit_return_page = submit_do_not_order.text

            # 提交后会返回新页面，又要改这些
            # Evil ASP.NET!
            form_param = get_web_forms_field(submit_return_page)
            submit_menu_form.update({
                '__VIEWSTATE': form_param[0],
                '__VIEWSTATEGENERATOR': form_param[1],
                '__EVENTVALIDATION': form_param[2]
            })

    # 提交菜单
    menu_param = gen_menu_param(course_amount)
    submit_menu_form.update({
        '__EVENTTARGET': '',
        '__CALLBACKID': '__Page',
        '__CALLBACKPARAM': menu_param
    })

    post_menu = post(
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
        student_id = input('\n输完按Enter\n请输入学号：')
        if len(student_id) == 7:
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
    calendar = Calendar.calendar_init()
    print('当前月份内，您可以选择以下日期')
    for month in calendar.values():
        for date in month:
            date_object = datetime.datetime.strptime(date, '%Y-%m-%d')
            print('{0} 星期{1}'.format(date, date_object.isoweekday()))
    # 说的是“72小时”，实际上是把那一整天排除了，故+1
    print("理论上说，现在能够订到", datetime.timedelta(3 + 1) + datetime.date.today(), "及以后的餐")

    while True:
        # 检查日期
        print('要是想得到别的月份的菜单，输一个那个月的日期')
        date = input('格式为：年-月-日，如：2015-9-30\n请输入日期：')
        # 首先，确认它是个正确的日期
        date_object = datetime.datetime.strptime(date, '%Y-%m-%d').date()
        # 统一宽度。这样就能够处理2015-9-3这种“格式错误”的日期了
        status = calendar.test(date_object)
        if status:
            pass
        else:
            if date_object.year not in calendar.selectable_year:
                print('请输入在')
                for year in calendar.selectable_year:
                    print(year)
                print('中的年份')
                continue
            elif len(calendar[date_object.strftime('%Y-%m')]) == 0:
                print('当前月份内无可订餐的日期')
            else:
                print('请输入')
                for month in calendar.values():
                    for date in month:
                        date_object = datetime.datetime.strptime(date, '%Y-%m-%d')
                        print('{0} 星期{1}'.format(date, date_object.isoweekday()))
                print('中的日期')

        # 拉菜单
        print('正在获取菜单')
        date = date_object.strftime('%Y-%m-%d')
        menu = Menu(date)
        course_amount = menu.get_course_amount()

        # 准备记录“不订餐”状态变化的餐次的列表
        to_select = []
        to_deselect = []

        print('{0}，星期{1}'.format(date, date_object.isoweekday()))
        for meal in menu:
            # 打印菜单
            print('\n{0}菜单'.format(MEAL_NAME[meal.id]))
            print('编号\t类别\t菜名\t\t单价\t最大份数\t订购份数\t订餐状态')
            for course in meal:
                print('\t'.join([
                    str(course.num),
                    course.type,
                    course.name,
                    str(course.price),
                    str(course.max),
                    str(course.current)
                ]))

            if meal.id in menu.do_not_order:
                print('\n此餐已被选上“不定餐”')
                do_not_order = True
            else:
                do_not_order = False

            # 修改菜单
            if not menu.mutable:
                print('菜单无法更改')
                continue
            else:
                print('\n菜单可更改')  # 如果菜单是可以提交的，那么最后一行会少3列。一般每行有9列。故在此插入换行符，以取得较统一的效果
                set_meal_selected = False

                order_status = input("请问您要定这一餐吗？输N不订餐，输其他字符继续").strip().capitalize()
                if 'N' in order_status:
                    # 由于浏览器的行为是在选中“不订餐”后立即向服务器发送状态变化的请求，而这么干有些浪费时间，故把这些留到最后提交
                    if not do_not_order:
                        to_select.append(meal.id)

                    # 用来占位，不然服务器不认
                    for course in meal:
                        course_amount[meal.id, course.id] = 0
                    continue
                else:
                    # 与上文的那个判断一起，为提交作准备
                    if do_not_order:
                        to_deselect.append(meal.id)

                    print('若您不需要改变订购份数，直接按Enter即可')
                    for course in meal:
                        print('\n编号：{0} 菜名：{1} 单价：{2} 最大份数：{3} 已定份数：{4}'.format(
                            course.num,
                            course.name,
                            course.price,
                            course.max,
                            course.current
                        ))
                        while not course.type == '必订菜':
                            course_num = input('请输入您要点的份数：')
                            # 如果直接敲Enter，就跳出循环，因为原始值已经在course_amount里了
                            if not course_num:
                                break
                            else:
                                course_num = int(course_num)
                                if 0 <= course_num <= course.max:
                                    course_amount[meal.id, course.id] = course_num  # 将份数放入字典
                                    # 订了套餐就不用特意去订必选菜了
                                    if course_num == 1 and course.type == '套餐':
                                        set_meal_selected = True
                                    break
                                else:
                                    print('请输入一个大于等于0且小于等于{0}的整数'.format(
                                        course.max))
                                    continue

                    # 放入必选菜
                    # 我也不知道会不会有某一餐有多道必选菜，所以最好还是不要写死了
                    if set_meal_selected:
                        course_num = 0
                    else:
                        course_num = 1

                    for course in meal.required_course:
                        course_amount[meal.id, course] = course_num

        if menu.mutable:
            print('正在提交菜单')
            do_not_order_list = [menu.do_not_order, to_select, to_deselect]
            post_status = submit_menu(
                date, course_amount,
                do_not_order_list, menu.form_param)

            if post_status:
                print('\n订餐成功')
            else:
                print('\n订餐失败')


if __name__ == "__main__":
    main()
