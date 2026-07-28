# -*- coding: utf-8 -*-

class PatchError(Exception):
    pass


class BackupError(PatchError):
    pass


class UndoError(PatchError):
    pass


class ValidationError(PatchError):
    pass


class SearchError(PatchError):
    pass


class MachOError(PatchError):
    pass
