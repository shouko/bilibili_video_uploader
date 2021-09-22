from collections import namedtuple

CDNProfile = namedtuple('CDNProfile', ['name', 'host'])

cdn_profiles = {
  name: CDNProfile(name, host)
  for name, host in [
    ['ws', 'upos-sz-upcdnws.bilivideo.com'],     # Wangsu
    ['qn', 'upos-sz-upcdnqn.bilivideo.com'],     # Qiniu
    ['hw', 'upos-sz-upcdnhw.bilivideo.com'],     # Huawei
    ['bda2', 'upos-sz-upcdnbda2.bilivideo.com'], # Baidu
  ]
}