NUMERIC_NUMBERS = {}
NUMERIC_NAMES = {}

def _numeric(number: str, name: str):
    NUMERIC_NUMBERS[number] = name
    NUMERIC_NAMES[name]     = number

_numeric("001", "RPL_WELCOME")
_numeric("005", "RPL_ISUPPORT")

_numeric("903", "RPL_SASLSUCCESS")
_numeric("904", "ERR_SASLFAIL")
_numeric("905", "ERR_SASLTOOLONG")
_numeric("906", "ERR_SASLABORTED")
_numeric("907", "ERR_SASLALREADY")
_numeric("908", "RPL_SASLMECHS")
