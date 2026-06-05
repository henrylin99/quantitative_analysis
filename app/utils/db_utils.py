import os
from dotenv import load_dotenv
import tushare as ts


load_dotenv()


class DatabaseUtils:
    # Tushare API token
    _tushare_token = os.getenv('TUSHARE_TOKEN') or os.getenv('tushare_token')

    @classmethod
    def init_tushare_api(cls):
        """
        初始化Tushare API
        :return: Tushare pro API对象
        """
        if not cls._tushare_token:
            raise ValueError('未配置TUSHARE_TOKEN，请在.env中设置后重试')
        return ts.pro_api(cls._tushare_token)
