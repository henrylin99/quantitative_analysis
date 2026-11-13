import os
from dotenv import load_dotenv
import tushare as ts


load_dotenv()


class DatabaseUtils:
    # Tushare API token：惰性读取（os.getenv），保证运行中通过设置页更新
    # TUSHARE_TOKEN 后无需重启即生效（历史版本在 import 时缓存导致必须重启）

    @classmethod
    def _get_token(cls):
        return os.getenv('TUSHARE_TOKEN') or os.getenv('tushare_token')

    @classmethod
    def init_tushare_api(cls):
        """
        初始化Tushare API
        :return: Tushare pro API对象
        """
        token = cls._get_token()
        if not token:
            raise ValueError('未配置TUSHARE_TOKEN，请在.env中设置后重试')
        return ts.pro_api(token)
