# -*- encoding: utf-8 -*-
"""
@File    :   bilibili_up.py
@Author  :   Joshua
@Contact :   froginwe11@163.com
@Time    :   2020/10/09 20:53:07
@Desc    :
"""
import re
import sys
import logging
import argparse
import webbrowser
from math import ceil
from json import dumps
from pathlib import Path
from time import sleep
from requests_html import HTMLSession
from requests.utils import cookiejar_from_dict

from cdn_profiles import cdn_profiles

class BiliAPI(object):
    """
    只有发布视频的功能，但也足够 :)
    """
    ua = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:71.0) Gecko/20100101 Firefox/71.0',
    }

    def __init__(self, sessdata, bili_jct, cdn):
        """
        登录cookies必要的两个参数，都可以从浏览器cookies中获取
        一定不要泄漏下面两个参数给别人，否则会有被盗号风险！！！

        sessdata: 登录凭证
        bili_jct: CSRF令牌
        """
        self.logger = logging.getLogger('Bilibili')
        self.SESSDATA = sessdata
        self.bili_jct = bili_jct
        self.auth_cookies = {
            'SESSDATA': sessdata,
            'bili_jct': bili_jct
        }
        self.session = HTMLSession()
        self.session.cookies = cookiejar_from_dict(self.auth_cookies)
        self.session.headers = self.ua
        self.cdn = cdn_profiles.get(cdn, 'ws')

    @classmethod
    def typelist(cls):
        """
        查看分区ID表格
        """
        try:
            webbrowser.open_new_tab(
                'https://gitee.com/nbody1996/bilibili-API-collect/blob/master/video/video_zone.md')
        except:
            pass
        finally:
            print('前往网页查看对应分区tID:\nhttps://gitee.com/nbody1996/bilibili-API-collect/blob/master/video/video_zone.md')

    def publish_video(self, file, *, atitle=None, adesc='', acopyright=2, asource='来源于网络', specified_type=None, specified_tags=None):
        """
        发布视频总入口

        file: 视频文件地址
        atitle: 指定视频标题
        adesc: 指定视频描述
        acopyright: 指定版权
        asource: 声明转载来源
        specified_type: 指定分区(int), 分区id详见`-l`参数
        specified_tags: 指定标签, 字符串逗号分隔
        """
        file = Path(file)
        assert file.exists(), f'不存在文件{file}'
        filename = file.name  # 文件名，带后缀
        filestem = atitle or file.stem  # 文件名，不包含后缀
        filesize = file.stat().st_size  # 文件大小

        self.logger.info(f'视频:{filestem}')

        # step 1
        self.logger.debug('开始预上传视频')
        res1 = self.preupload(filename=filename, filesize=filesize)
        upos_uri = res1['upos_uri'].split('//')[-1]
        auth = res1['auth']
        biz_id = res1['biz_id']
        chunk_size = res1['chunk_size']
        chunks = ceil(filesize/chunk_size)  # 批次

        # step 2
        self.logger.debug(f'准备上传视频')
        res2 = self.upload_post(upos_uri=upos_uri, auth=auth)
        upload_id = res2['upload_id']
        key = res2['key']
        # 存于bilibili的视频文件名(无后缀)
        bfilestem = re.search(r'/(.*)\.', key).group(1)

        # step 3
        self.logger.debug(f'分{chunks}个批次上传视频')
        fileio = file.open(mode='rb')
        self.upload_put(
            upos_uri=upos_uri,
            auth=auth,
            upload_id=upload_id,
            fileio=fileio,
            filesize=filesize,
            chunk_size=chunk_size,
            chunks=chunks
        )
        fileio.close()

        # step 4
        self.upload_finish(upos_uri=upos_uri, auth=auth, filename=filename,
                           upload_id=upload_id, biz_id=biz_id, chunks=chunks)

        # 选择分区
        typeid = specified_type or self.choose_type(
            title=filestem, bfilestem=bfilestem, desc=adesc)[0]

        # 选择标签
        if not specified_tags:
            tags = self.choose_tags(
                title=filestem, bfilestem=bfilestem, typeid=typeid, desc=adesc)
            tags_text = ','.join(tags)  # 以逗号分隔
        else:
            tags_text = specified_tags

        # 获取视频封面
        cover_url = self.choose_cover(bfilestem=bfilestem)[0]

        # 发布视频
        self.pre_add()
        res = self.add(bfilestem=bfilestem, filestem=filestem,
                       typeid=typeid, tags=tags_text, copyright=acopyright, desc=adesc, cover_url=cover_url, source=asource)
        aid = res['data']['aid']
        bvid = res['data']['bvid']
        self.logger.info(
            f'[{filestem}]发布成功\naid:{aid}\tbvid:{bvid}\n分区ID:{typeid}\t标签:{tags_text}')

    def pre_add(self):
        url = 'https://member.bilibili.com/x/geetest/pre/add'
        self.session.get(url, headers={'TE': 'Trailers'})

    def add(self, bfilestem, filestem, typeid, tags, source='来源于网络', copyright=2, desc='', cover_url=''):
        """
        发布视频
        不能发布太频繁, B站官方限制**30秒一稿**

        bfilestem: 存于bilibili的视频文件名(无后缀)
        filestem: 视频标题
        typeid: 分区id
        tags: 标签，逗号分隔
        source: 来源(转载必要)
        copyright: 1自制 2转载
        desc: 视频简介
        cover_url: 封面链接
        """
        url = f'https://member.bilibili.com/x/vu/web/add?csrf={self.bili_jct}'
        data = {'copyright': copyright,  # 转载
                'videos': [{'filename': bfilestem,
                            'title': filestem,
                            'desc': desc}],
                'source': source,  # 来源
                'tid': typeid,  # 分区id
                # //i0.hdslb.com/bfs/archive/5eb44a83a7b6466a10eef02a044024784462e3fc.jpg
                'cover': cover_url,  # 封面url 可以不加，b站后台会自动添加
                'title': filestem,  # 标题
                'tag': tags,  # 标签
                'desc_format_id': 0,  # ?
                'desc': desc,  # 视频简介
                'dynamic': filestem + '\n' + desc,  # 动态?
                'subtitle': {'open': 0, 'lan': ''}}  # 分P相关
        # 自制包含:interactive:0; no_reprint:1; copyright:1;
        if copyright != 2:
            del data['source']
            data['copyright'] = 1
            data['interactive'] = 0
            data['no_reprint'] = 1
        res_json = self.session.post(url, json=data, headers={
                                     'TE': 'Trailers'}).json()
        return res_json

    def choose_cover(self, *, bfilestem, wait_sec=2):
        """
        轮询等待封面获取

        bfilestem: 存于bilibili的视频文件名(无后缀)
        wait_sec: 等待秒数
        """
        url = f'https://member.bilibili.com/x/web/archive/recovers?fns={bfilestem}'

        while True:
            res_json = self.session.get(
                url, headers={'TE': 'Trailers'}).json()
            allow_covers = res_json['data']
            if allow_covers:
                return allow_covers
            sleep(wait_sec)
            self.logger.debug('等待封面获取中...')

    def choose_type(self, *, title, bfilestem=None, desc=''):
        """
        选择分区

        title: 视频标题
        bfilestem: 存于bilibili的视频文件名(无后缀)
        desc: 视频简介
        """
        url = 'https://member.bilibili.com/x/web/archive/typeid'
        params = {
            'title': title,
            'filename':	bfilestem,
            'desc': desc,  # 视频简介
            'cover': '',
            'groupid': 1,  # 暂不清楚用处
            'vfea': ''
        }
        res_json = self.session.get(url, params=params, headers={
                                    'TE': 'Trailers'}).json()
        # print(dumps(res_json, ensure_ascii=False), end='\n'+'-'*50+'\n')
        best_type = [(i['id'], i['name']) for i in res_json['data']][0]
        return best_type

    def choose_tags(self, *, title, bfilestem=None, typeid='', desc='', limit=10):
        """
        选择标签

        title: 视频标题
        bfilestem: 存于bilibili的视频文件名(无后缀)
        typeid: 分区id
        limit: 10个标签，B站允许最多10个标签
        """
        url = 'https://member.bilibili.com/x/web/archive/tags'
        params = {
            'typeid': '',  # TODO:添加分区貌似有问题，先为空
            'title': title,
            'filename':	bfilestem,
            'desc': desc,
            'cover': '',
            'groupid': 1,
            'vfea': ''
        }
        res_json = self.session.get(url, params=params,  headers={
                                    'TE': 'Trailers'}).json()
        # print(dumps(res_json, ensure_ascii=False), end='\n'+'-'*50+'\n')
        tags = [i['tag'] for i in res_json['data']]
        if limit:
            tags = tags[:limit]
        return tags

    def preupload(self, *, filename, filesize):
        """
        预上传视频

        filename: 视频文件名，带后缀
        filesize: 视频大小
        """
        url = 'https://member.bilibili.com/preupload'
        params = {
            'name':	filename,  # 视频名
            'size':	filesize,  # 视频尺寸
            'r': 'upos',
            'profile': 'ugcupos/bup',
            'ssl':	0,
            'version':	'2.8.9',
            'build': '2080900',
            'upcdn': self.cdn.name,
            'probe_version':	'20200810'  # TODO:跟日期相关，可能会改动
        }
        res_json = self.session.get(
            url,
            params=params,
            headers={'TE': 'Trailers'}
        ).json()
        # print(dumps(res_json, ensure_ascii=False, indent=2), end='\n'+'-'*50+'\n')
        assert res_json['OK'] == 1
        self.logger.debug('预上传成功')
        return res_json

    def upload_post(self, *, upos_uri, auth):
        """
        上传视频前的准备工作

        upos_uri: preupload返回值
        auth: preupload返回值
        """
        url = f'https://{self.cdn.host}/{upos_uri}?uploads&output=json'
        res_json = self.session.post(url, headers={'X-Upos-Auth': auth}).json()
        # print(dumps(res_json, ensure_ascii=False, indent=2), end='\n'+'-'*50+'\n')
        assert res_json['OK'] == 1
        self.logger.debug('上传准备阶段成功')
        return res_json

    def upload_put(self, *, upos_uri, auth, upload_id, fileio, filesize, chunk_size, chunks):
        """
        分批上传视频

        upos_uri: preupload返回值
        auth: preupload返回值
        upload_id: upload_post返回值
        fileio: 视频文件的io流
        filesize: 视频文件大小
        chunk_size: 一个批次上传多大字节的视频，preupload返回值
        chunks: 计算得出的该分多少批次上传
        """
        url = f'https://{self.cdn.host}/{upos_uri}'
        params = {
            'partNumber': None,  # 1开始
            'uploadId':	upload_id,
            'chunk':	None,  # 0开始
            'chunks':	chunks,
            'size':	None,  # 当前批次size
            'start':	None,
            'end':	None,
            'total':	filesize,
        }
        for batchno in range(chunks):
            start = fileio.tell()
            batchbytes = fileio.read(chunk_size)
            params['partNumber'] = batchno + 1
            params['chunk'] = batchno
            params['size'] = len(batchbytes)
            params['start'] = start
            params['end'] = fileio.tell()
            res = self.session.put(url, params=params, data=batchbytes, headers={
                                   'X-Upos-Auth': auth})
            assert res.status_code == 200
            self.logger.debug(f'批次{batchno+1}上传成功')

    def upload_finish(self, *, upos_uri, auth, filename, upload_id, biz_id, chunks):
        """
        通知视频已上传完毕

        upos_uri: preupload返回值
        auth: preupload返回值
        filename: 视频文件名，带后缀
        upload_id: upload_post返回值
        biz_id: preupload返回值
        chunks:批次
        """
        url = f'https://{self.cdn.host}/{upos_uri}'
        params = {
            'output':	'json',
            'name':	filename,
            'profile'	: 'ugcupos/bup',
            'uploadId':	upload_id,
            'biz_id':	biz_id
        }
        data = {"parts": [{"partNumber": i, "eTag": "etag"}
                          for i in range(chunks, 1)]}
        res_json = self.session.post(url, params=params, json=data,
                                     headers={'X-Upos-Auth': auth}).json()
        assert res_json['OK'] == 1


def script_main():
    parser = argparse.ArgumentParser(description='一个B站上传发布视频的小工具 :)')
    parser.add_argument('video_path', nargs='?', help='视频文件路径')
    parser.add_argument('-c', '--copyright', type=int,
                        default=2, help='类型: 1为自制 2为转载。默认为2')
    parser.add_argument('-s', '--source', default='来源于网络',
                        help='来源声明(转载必要), 默认为"来源于网络"')
    parser.add_argument('-t', '--title', help='标题, 不加即为视频文件名')
    parser.add_argument('--desc', default='', help='视频描述, 默认为空')
    parser.add_argument('-d', '--debug', action='store_true',
                        default=False, help='调试模式，更详细的输出')
    parser.add_argument('-l', '--typelist',
                        action='store_true', help='查看分区列表')
    parser.add_argument('-tid', '--typeid', type=int,
                        help='视频分区id(使用-l参数查看), 不指定则使用推荐分区')
    parser.add_argument('-ta', '--tags', help='视频标签, 英文逗号分隔, 不指定则使用推荐标签')
    parser.add_argument('-sd', '--sessdata',
                        help='身份验证cookie(上传必要), 浏览器cookies中获取')
    parser.add_argument('-bj', '--bili_jct',
                        help='CSRF身份验证cookie(上传必要), 浏览器cookies中获取')
    parser.add_argument('-cdn', '--cdn', default='auto', help='上傳CDN名稱, 預設使用Wangsu')

    args = parser.parse_args()

    if args.typelist:
        BiliAPI.typelist()
        sys.exit()

    if not all((args.video_path, args.sessdata, args.bili_jct)):
        print('video_path, sessdata, bili_jct这三个参数，上传视频是必要的', end='\n'*2)
        parser.print_help()
        sys.exit()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    BiliAPI(
        args.sessdata,
        args.bili_jct,
        args.cdn
    ).publish_video(
        args.video_path,
        atitle=args.title,
        adesc=args.desc,
        acopyright=args.copyright,
        asource=args.source,
        specified_type=args.typeid,
        specified_tags=args.tags
    )


if __name__ == '__main__':
    script_main()
