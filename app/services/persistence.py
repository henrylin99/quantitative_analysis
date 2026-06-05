from app.extensions import db


def persist_new(instance):
    db.session.add(instance)
    db.session.commit()
    return instance


def persist_changes(instance):
    db.session.commit()
    return instance


def remove_instance(instance):
    db.session.delete(instance)
    db.session.commit()
    return True
