def escape_markdown(text):
    special_chars = ['_', '*', '~', '`', "'", '|']
    for char in special_chars:
        text = text.replace(char, '\\' + char)
    return text