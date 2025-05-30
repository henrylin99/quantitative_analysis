from flask import Blueprint

main_bp = Blueprint('main', __name__)

from . import views 