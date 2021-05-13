from distutils.core import setup

setup(
  name='JustChatting',
  version='1.0',
  description='A live-chat server',
  author='Aaron Gill-Braun',
  packages=['jc', 'jc.server', 'jc.db'],
)
