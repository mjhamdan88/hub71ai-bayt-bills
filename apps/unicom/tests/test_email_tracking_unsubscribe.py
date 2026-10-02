from unicom.views.email_tracking import is_unsubscribe_url


def test_is_unsubscribe_url_detects_relative_and_absolute(settings):
    settings.UNICRM_UNSUBSCRIBE_PATH = '/unicrm/unsubscribe/'
    assert is_unsubscribe_url('/unicrm/unsubscribe/?token=abc')
    assert is_unsubscribe_url('https://example.com/unicrm/unsubscribe/?token=abc')
    assert is_unsubscribe_url('https://example.com/unicrm/unsubscribe/extra/path')
    assert not is_unsubscribe_url('https://example.com/other/path')
    assert not is_unsubscribe_url('/different/path')
