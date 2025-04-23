

class SpotifyBaseException(Exception):
    ...


class SpotifyException(SpotifyBaseException):
    def __init__(self, http_status, code, msg, reason=..., headers=...) -> None:
        ...




class SpotifyOauthError(SpotifyBaseException):

    def __init__(self, message, error=..., error_description=..., *args, **kwargs) -> None:
        ...



class SpotifyStateError(SpotifyOauthError):

    def __init__(self, local_state=..., remote_state=..., message=..., error=..., error_description=..., *args, **kwargs) -> None:
        ...



