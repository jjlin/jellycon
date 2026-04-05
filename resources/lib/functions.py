from __future__ import (
    division, absolute_import, print_function, unicode_literals
)

import sys
import os
import time
import cProfile
import pstats

import xbmcplugin
import xbmcgui
import xbmcaddon
import xbmc
from six import StringIO
from six.moves.urllib.parse import quote, unquote, parse_qsl, urlencode

from .jellyfin import api
from .utils import (
    translate_string, get_version, load_user_details, get_art_url,
    get_default_filters, translate_path, kodi_version, get_jellyfin_url
)
from .kodi_utils import HomeWindow
from .datamanager import clear_cached_server_data
from .server_detect import check_server, check_connection_speed
from .lazylogger import LazyLogger
from .menu_functions import (
    display_main_menu, display_menu, show_movie_alpha_list,
    show_tvshow_alpha_list, show_genre_list, show_search,
    show_movie_pages, show_artist_alpha_list
)
from .server_sessions import show_server_sessions
from .action_menu import ActionMenu
from .dialogs import BitrateDialog
from .widgets import (
    get_widget_content, get_widget_content_cast, check_for_new_content
)
from .cache_images import CacheArtwork
from .dir_functions import get_content, process_directory
from .tracking import timer
from .skin_cloner import clone_default_skin
from .play_utils import play_file

__addon__ = xbmcaddon.Addon()
__addondir__ = translate_path(__addon__.getAddonInfo('profile'))
__cwd__ = __addon__.getAddonInfo('path')
PLUGINPATH = translate_path(os.path.join(__cwd__))
addon_id = __addon__.getAddonInfo('id')

log = LazyLogger(__name__)

user_details = load_user_details()


@timer
def main_entry_point():
    log.debug("===== JellyCon START =====")

    settings = xbmcaddon.Addon()
    profile_count = int(settings.getSetting('profile_count'))
    pr = None
    if profile_count > 0:
        profile_count = profile_count - 1
        settings.setSetting('profile_count', str(profile_count))
        pr = cProfile.Profile()
        pr.enable()

    log.debug(f"Running Python: {sys.version_info}")
    log.debug(f"Running JellyCon: {get_version()}")
    log.debug(f"Kodi BuildVersion: {xbmc.getInfoLabel('System.BuildVersion')}"
    )
    log.debug(f"Kodi Version: {kodi_version()}")
    log.debug(f"Script argument data: {sys.argv}")

    params = get_params()
    log.debug(f"Script params: {params}")

    request_path = params.get("request_path", None)
    param_url = params.get('url', None)

    mode = params.get("mode", None)

    if (len(params) == 1 and request_path
            and request_path.find("/library/movies") > -1):

        check_server()
        new_params = {}
        new_params["item_type"] = "Movie"
        new_params["media_type"] = "movies"
        show_content(new_params)
    elif mode == "CHANGE_USER":
        check_server(change_user=True, notify=False)
    elif mode == "CACHE_ARTWORK":
        CacheArtwork().cache_artwork_interactive()
    elif mode == "DETECT_SERVER":
        check_server(force=True, notify=True)
    elif mode == "DETECT_SERVER_USER":
        check_server(force=True, change_user=True, notify=False)
    elif mode == "DETECT_CONNECTION_SPEED":
        check_connection_speed()
    elif mode == "playTrailer":
        item_id = params["id"]
        play_item_trailer(item_id)
    elif mode == "MOVIE_ALPHA":
        show_movie_alpha_list(params)
    elif mode == "TVSHOW_ALPHA":
        show_tvshow_alpha_list(params)
    elif mode == "ARTIST_ALPHA":
        show_artist_alpha_list(params)
    elif mode == "GENRES":
        show_genre_list(params)
    elif mode == "MOVIE_PAGES":
        show_movie_pages(params)
    elif mode == "TOGGLE_WATCHED":
        toggle_watched(params)
    elif mode == "SHOW_MENU":
        show_menu(params)
    elif mode == "CLONE_SKIN":
        clone_default_skin()
    elif mode == "SHOW_SETTINGS":
        __addon__.openSettings()
        window = xbmcgui.getCurrentWindowId()
        if window == 10000:
            log.debug(
                "Currently in home - refresh to allow new settings to be taken"
            )
            xbmc.executebuiltin("ActivateWindow(Home)")
    elif mode == "CLEAR_CACHE":
        clear_cached_server_data()
    elif mode == "WIDGET_CONTENT":
        get_widget_content(int(sys.argv[1]), params)
    elif mode == "WIDGET_CONTENT_CAST":
        get_widget_content_cast(int(sys.argv[1]), params)
    elif mode == "SHOW_CONTENT":
        check_server()
        show_content(params)
    elif mode == "SEARCH":
        xbmcplugin.setContent(int(sys.argv[1]), 'files')
        show_search()
    elif mode == "NEW_SEARCH":
        search_results(params)
    elif mode == "NEW_SEARCH_PERSON":
        search_results_person(params)
    elif mode == "SHOW_SERVER_SESSIONS":
        show_server_sessions()
    elif mode == "SHOW_ADDON_MENU":
        display_menu(params)
    else:
        log.debug(f"JellyCon -> Mode: {mode}")
        log.debug(f"JellyCon -> URL: {param_url}")

        if mode == "GET_CONTENT":
            get_content(param_url, params)
        elif mode == "PLAY":
            play_action(params)
        else:
            check_server()
            display_main_menu()

    if pr:
        pr.disable()

        file_time_stamp = time.strftime("%Y%m%d-%H%M%S")
        tab_file_name = f"{__addondir__}-profile({file_time_stamp}).txt"
        s = StringIO()
        ps = pstats.Stats(pr, stream=s)
        ps = ps.sort_stats('cumulative')
        ps.print_stats()
        ps.strip_dirs()
        ps = ps.sort_stats('tottime')
        ps.print_stats()
        with open(tab_file_name, 'w') as f:
            f.write(s.getvalue())

    log.debug("===== JellyCon FINISHED =====")


def toggle_watched(params):
    log.debug(f"toggle_watched: {params}")
    item_id = params.get("item_id", None)
    if item_id is None:
        return
    url = f"/Users/{api.user_id}/Items/{item_id}?format=json"
    result = api.get(url)
    log.debug(f"toggle_watched item info: {result}")

    user_data = result.get("UserData", None)
    if user_data is None:
        return

    if user_data.get("Played", False) is False:
        mark_item_watched(item_id)
    else:
        mark_item_unwatched(item_id)


def mark_item_watched(item_id):
    log.debug(f"Mark Item Watched: {item_id}")
    url = f"/Users/{api.user_id}/PlayedItems/{item_id}"
    api.post(url)
    check_for_new_content()
    home_window = HomeWindow()
    last_url = home_window.get_property("last_content_url")
    if last_url:
        log.debug(f"markWatched_lastUrl: {last_url}")
        home_window.set_property(f"skip_cache_for_{last_url}", "true")

    xbmc.executebuiltin("Container.Refresh")


def mark_item_unwatched(item_id):
    log.debug(f"Mark Item UnWatched: {item_id}")
    url = f"/Users/{api.user_id}/PlayedItems/{item_id}"
    api.delete(url)
    check_for_new_content()
    home_window = HomeWindow()
    last_url = home_window.get_property("last_content_url")
    if last_url:
        log.debug(f"markUnwatched_lastUrl: {last_url}")
        home_window.set_property(f"skip_cache_for_{last_url}", "true")

    xbmc.executebuiltin("Container.Refresh")


def mark_item_favorite(item_id):
    log.debug(f"Add item to favourites: {item_id}")
    url = f"/Users/{api.user_id}/FavoriteItems/{item_id}"
    api.post(url)
    check_for_new_content()
    home_window = HomeWindow()
    last_url = home_window.get_property("last_content_url")
    if last_url:
        home_window.set_property(f"skip_cache_for_{last_url}", "true")

    xbmc.executebuiltin("Container.Refresh")


def unmark_item_favorite(item_id):
    log.debug(f"Remove item from favourites: {item_id}")
    url = f"/Users/{api.user_id}/FavoriteItems/{item_id}"
    api.delete(url)
    check_for_new_content()
    home_window = HomeWindow()
    last_url = home_window.get_property("last_content_url")
    if last_url:
        home_window.set_property(f"skip_cache_for_{last_url}", "true")

    xbmc.executebuiltin("Container.Refresh")


def delete(item_id):
    item = api.get(f"/Users/{api.user_id}/Items/{item_id}")

    item_id = item.get("Id")
    item_name = item.get("Name", "")
    series_name = item.get("SeriesName", "")
    ep_number = item.get("IndexNumber", -1)

    final_name_parts = []

    if series_name:
        final_name_parts.append(series_name)

    if ep_number != -1:
        final_name_parts.append(f"Episode {ep_number:02d}")

    final_name_parts.append(item_name)
    final_name = " - ".join(final_name_parts)

    if not item.get("CanDelete", False):
        xbmcgui.Dialog().ok(
            translate_string(30135), translate_string(30417), final_name
        )
        return

    return_value = xbmcgui.Dialog().yesno(
        translate_string(30091), f'{final_name}\n{translate_string(30092)}'
    )
    if return_value:
        log.debug(f'Deleting Item: {item_id}')
        url = f'/Items/{item_id}'
        progress = xbmcgui.DialogProgress()
        progress.create(translate_string(30052), translate_string(30053))
        api.delete(url)
        progress.close()
        check_for_new_content()
        home_window = HomeWindow()
        last_url = home_window.get_property("last_content_url")
        if last_url:
            home_window.set_property(
                f"skip_cache_for_{last_url}", "true"
            )

        xbmc.executebuiltin("Container.Refresh")


def get_params():
    '''
    Retrieve the request data from Kodi
    '''

    plugin_path = sys.argv[0]
    paramstring = sys.argv[2]

    log.debug(f"Parameter string: {paramstring}")
    log.debug(f"Plugin Path string: {plugin_path}")

    param = dict(parse_qsl(paramstring[1:]))

    # add plugin path
    request_path = plugin_path.replace(f"plugin://{addon_id}", "")
    param["request_path"] = request_path

    log.debug(f"JellyCon -> Detected parameters: {param}")
    return param


def show_menu(params):
    log.debug(f"showMenu(): {params}")

    home_window = HomeWindow()
    settings = xbmcaddon.Addon()
    item_id = params["item_id"]

    url = f"/Users/{api.user_id}/Items/{item_id}?format=json"
    result = api.get(url)
    log.debug(f"Menu item info: {result}")

    if result is None:
        return

    action_items = []

    # Additional items to include in the context menu for different item types
    if result["Type"] in ["Episode", "Movie", "Music", "Video", "Audio",
                          "TvChannel", "Program", "MusicVideo"]:
        li = xbmcgui.ListItem(translate_string(30314), offscreen=True)
        li.setProperty('menu_id', 'play')
        action_items.append(li)

    if result["Type"] in ["Season", "MusicArtist", "MusicAlbum", "Playlist",
                          "MusicGenre"]:
        li = xbmcgui.ListItem(translate_string(30317), offscreen=True)
        li.setProperty('menu_id', 'play_all')
        action_items.append(li)

    if result["Type"] in ["MusicArtist", "MusicAlbum", "Playlist",
                          "Series", "Season", "MusicGenre"]:
        li = xbmcgui.ListItem(translate_string(30448), offscreen=True)
        li.setProperty('menu_id', 'shuffle')
        action_items.append(li)

    if result["Type"] in ["MusicArtist", "MusicAlbum", "Audio"]:
        li = xbmcgui.ListItem(translate_string(30449), offscreen=True)
        li.setProperty('menu_id', 'instant_mix')
        action_items.append(li)

    if result["Type"] in ["Episode", "Movie", "Video", "TvChannel",
                          "Program", "MusicVideo"]:
        li = xbmcgui.ListItem(translate_string(30275), offscreen=True)
        li.setProperty('menu_id', 'transcode')
        action_items.append(li)

    if result["Type"] in ["Episode", "Movie", "Music", "Video", "Audio",
                          "MusicArtist", "MusicAlbum", "MusicVideo",
                          "MusicGenre"]:
        li = xbmcgui.ListItem(translate_string(30402), offscreen=True)
        li.setProperty('menu_id', 'add_to_playlist')
        action_items.append(li)

    if result["Type"] in ("Movie", "Series"):
        li = xbmcgui.ListItem(translate_string(30307), offscreen=True)
        li.setProperty('menu_id', 'play_trailer')
        action_items.append(li)

    if result["Type"] == "Episode" and result["ParentId"] is not None:
        li = xbmcgui.ListItem(translate_string(30327), offscreen=True)
        li.setProperty('menu_id', 'view_season')
        action_items.append(li)

    if result["Type"] in ("Series", "Season", "Episode"):
        li = xbmcgui.ListItem(translate_string(30354), offscreen=True)
        li.setProperty('menu_id', 'view_series')
        action_items.append(li)

    if result["Type"] == "Movie":
        li = xbmcgui.ListItem("Show Extras", offscreen=True)
        li.setProperty('menu_id', 'show_extras')
        action_items.append(li)

    user_data = result.get("UserData", None)
    if user_data:
        progress = user_data.get("PlaybackPositionTicks", 0) != 0
        played = user_data.get("Played", False)
        if not played or progress:
            li = xbmcgui.ListItem(translate_string(30270), offscreen=True)
            li.setProperty('menu_id', 'mark_watched')
            action_items.append(li)
        if played or progress:
            li = xbmcgui.ListItem(translate_string(30271), offscreen=True)
            li.setProperty('menu_id', 'mark_unwatched')
            action_items.append(li)

        if user_data.get("IsFavorite", False) is False:
            li = xbmcgui.ListItem(translate_string(30272), offscreen=True)
            li.setProperty('menu_id', 'jellyfin_set_favorite')
            action_items.append(li)
        else:
            li = xbmcgui.ListItem(translate_string(30273), offscreen=True)
            li.setProperty('menu_id', 'jellyfin_unset_favorite')
            action_items.append(li)

    can_delete = result.get("CanDelete", False)
    if can_delete:
        li = xbmcgui.ListItem(translate_string(30274), offscreen=True)
        li.setProperty('menu_id', 'delete')
        action_items.append(li)

    li = xbmcgui.ListItem(translate_string(30398), offscreen=True)
    li.setProperty('menu_id', 'refresh_server')
    action_items.append(li)

    li = xbmcgui.ListItem(translate_string(30281), offscreen=True)
    li.setProperty('menu_id', 'refresh_images')
    action_items.append(li)

    if result["Type"] in ["Movie", "Series"]:
        li = xbmcgui.ListItem(translate_string(30399), offscreen=True)
        li.setProperty('menu_id', 'hide')
        action_items.append(li)

    li = xbmcgui.ListItem(translate_string(30401), offscreen=True)
    li.setProperty('menu_id', 'info')
    action_items.append(li)

    window = xbmcgui.Window(xbmcgui.getCurrentWindowId())
    container_view_id = str(window.getFocusId())
    container_content_type = xbmc.getInfoLabel("Container.Content")
    view_key = f"view-{container_content_type}"
    current_default_view = settings.getSetting(view_key)
    view_match = container_view_id == current_default_view
    log.debug(f"View ID:{container_view_id} Content type:{container_content_type}"
    )

    if container_content_type in ["movies", "tvshows", "seasons",
                                  "episodes", "sets"]:
        if view_match:
            li = xbmcgui.ListItem("Unset as default view", offscreen=True)
            li.setProperty('menu_id', 'unset_view')
            action_items.append(li)
        else:
            li = xbmcgui.ListItem("Set as default view", offscreen=True)
            li.setProperty('menu_id', 'set_view')
            action_items.append(li)

    action_menu = ActionMenu("ActionMenu.xml", PLUGINPATH, "default", "720p")
    action_menu.setActionItems(action_items)
    action_menu.doModal()
    selected_action_item = action_menu.getActionItem()
    selected_action = ""
    if selected_action_item is not None:
        selected_action = selected_action_item.getProperty('menu_id')
    log.debug(f"Menu Action Selected: {selected_action}")
    del action_menu

    if selected_action == "play":
        log.debug("Play Item")
        play_action(params)

    elif selected_action == "set_view":
        log.debug(f"Setting view type for {view_key} to {container_view_id}"
        )
        settings.setSetting(view_key, container_view_id)

    elif selected_action == "unset_view":
        log.debug(f"Un-Settign view type for {view_key} to {container_view_id}"
        )
        settings.setSetting(view_key, "")

    elif selected_action == "refresh_server":
        url_path = f"/Items/{item_id}/Refresh"
        url_params = {
            "Recursive": True,
            "ImageRefreshMode": "FullRefresh",
            "MetadataRefreshMode": "FullRefresh",
            "ReplaceAllImages": True,
            "ReplaceAllMetadata": True
        }

        url = get_jellyfin_url(url_path, url_params)
        res = api.post(url)
        log.debug(f"Refresh Server Response: {res}")

    elif selected_action == "hide":
        user_details = load_user_details()
        user_name = user_details["user_name"]
        hide_tag_string = "hide-" + user_name
        url = f"/Items/{item_id}/Tags/Add"
        post_tag_data = {"Tags": [{"Name": hide_tag_string}]}
        res = api.post(url, post_tag_data)
        log.debug(f"Add Tag Response: {res}")

        check_for_new_content()

        last_url = home_window.get_property("last_content_url")
        if last_url:
            log.debug(f"markUnwatched_lastUrl: {last_url}")
            home_window.set_property(
                f"skip_cache_for_{last_url}", "true"
            )

        xbmc.executebuiltin("Container.Refresh")

    elif selected_action == "play_all":
        play_action(params)

    elif selected_action == "shuffle":
        params["action"] = "shuffle"
        play_action(params)

    elif selected_action == "instant_mix":
        params["action"] = "instant_mix"
        play_action(params)

    elif selected_action == "play_trailer":
        play_item_trailer(item_id)

    elif selected_action == "transcode":
        params['force_transcode'] = 'true'

        max_bitrate = settings.getSetting("force_max_stream_bitrate")
        initial_bitrate_value = int(max_bitrate)
        bitrate_dialog = BitrateDialog(
            "BitrateDialog.xml", PLUGINPATH, "default", "720p"
        )
        bitrate_dialog.initial_bitrate_value = initial_bitrate_value
        bitrate_dialog.doModal()
        selected_transcode_value = bitrate_dialog.selected_transcode_value
        del bitrate_dialog
        log.debug(f"selected_transcode_value: {selected_transcode_value}"
        )

        if selected_transcode_value > 0:
            settings.setSetting(
                "force_max_stream_bitrate", str(selected_transcode_value))

            play_action(params)

    elif selected_action == "add_to_playlist":
        params["action"] = "add_to_playlist"
        play_action(params)

    elif selected_action == "jellyfin_set_favorite":
        mark_item_favorite(item_id)

    elif selected_action == "jellyfin_unset_favorite":
        unmark_item_favorite(item_id)

    elif selected_action == "mark_watched":
        mark_item_watched(item_id)

    elif selected_action == "mark_unwatched":
        mark_item_unwatched(item_id)

    elif selected_action == "delete":
        delete(item_id)

    elif selected_action == "show_extras":
        url = f"/Users/{api.user_id}/Items/{item_id}/SpecialFeatures"
        plugin_params = {
            "url": url,
            "mode": "GET_CONTENT",
            "media_type": "Videos"
        }

        action_params = urlencode(plugin_params)

        action_url = f"plugin://{addon_id}/?{action_params}"
        built_in_command = f'ActivateWindow(Videos, {action_url}, return)'
        xbmc.executebuiltin(built_in_command)

    elif selected_action == "view_season":
        xbmc.executebuiltin("Dialog.Close(all,true)")
        parent_id = result["ParentId"]
        series_id = result["SeriesId"]

        url_path = f"/Shows/{series_id}/Episodes"
        url_params = {
            "userId": api.user_id,
            "seasonId": parent_id,
            "IsVirtualUnAired": False,
            "IsMissing": False,
            "Fields": f"SpecialEpisodeNumbers,{get_default_filters()}"
        }

        url = get_jellyfin_url(url_path, url_params)

        plugin_params = {
            "url": url,
            "mode": "GET_CONTENT",
            "media_type": "Season"
        }

        action_params = urlencode(plugin_params)

        action_url = f"plugin://{addon_id}/?{action_params}"
        built_in_command = f'ActivateWindow(Videos, {action_url}, return)'
        xbmc.executebuiltin(built_in_command)

    elif selected_action == "view_series":
        xbmc.executebuiltin("Dialog.Close(all,true)")

        series_id = result["SeriesId"]
        if not series_id:
            series_id = item_id

        url_path = f"/Shows/{series_id}/Seasons"
        url_params = {
            "userId": api.user_id,
            "Fields": get_default_filters(),
        }

        url = get_jellyfin_url(url_path, url_params)

        plugin_params = {
            "url": url,
            "mode": "GET_CONTENT",
            "media_type": "Series"
        }

        action_params = urlencode(plugin_params)

        action_url = f"plugin://{addon_id}/?{action_params}"

        if xbmc.getCondVisibility("Window.IsActive(home)"):
            built_in_command = f'ActivateWindow(Videos, {action_url}, return'
        else:
            built_in_command = f'Container.Update({action_url})'

        xbmc.executebuiltin(built_in_command)

    elif selected_action == "refresh_images":
        CacheArtwork().delete_cached_images(item_id)

    elif selected_action == "info":
        xbmc.executebuiltin("Dialog.Close(all,true)")
        xbmc.executebuiltin("Action(info)")


def show_content(params):
    log.debug(f"showContent Called: {params}")

    item_type = params.get("item_type")
    settings = xbmcaddon.Addon()
    group_movies = settings.getSetting('group_movies') == "true"

    if item_type.lower().find("movie") == -1:
        group_movies = False

    url_path = f"/Users/{api.user_id}/Items"
    url_params = {
        "ImageTypeLimit": 1,
        "IsMissing": False,
        "Fields": get_default_filters(),
        "CollapseBoxSetItems": group_movies,
        "GroupItemsIntoCollections": group_movies,
        "Recursive": True,
        "SortBy": "Name",
        "SortOrder": "Ascending",
        "IsVirtualUnaired": False,
        "IncludeItemTypes": item_type
    }

    content_url = get_jellyfin_url(url_path, url_params)

    log.debug(f"showContent Content Url: {content_url}")
    get_content(content_url, params)


def search_results_person(params):

    handle = int(sys.argv[1])

    person_id = params.get("person_id")

    url_path = f"/Users/{api.user_id}/Items"
    url_params = {
        "PersonIds": person_id,
        "Recursive": True,
        "Fields": get_default_filters()
    }

    details_url = get_jellyfin_url(url_path, url_params)

    params["name_format"] = "Episode|episode_name_format"

    dir_items, detected_type, total_records = process_directory(
        details_url, None, params
    )

    log.debug(f'search_results_person results: {dir_items}')
    log.debug(f'search_results_person detect_type: {detected_type}')

    if detected_type is not None:
        # if the media type is not set then try to use the detected type
        log.debug(f"Detected content type: {detected_type}")
        content_type = None

        if detected_type == "Movie":
            content_type = 'movies'
        elif detected_type == "Episode":
            content_type = 'episodes'
        elif detected_type == "Series":
            content_type = 'tvshows'
        elif detected_type in ["Music", "Audio", "Musicalbum"]:
            content_type = 'songs'

        if content_type:
            xbmcplugin.setContent(handle, content_type)

    if dir_items is not None:
        xbmcplugin.addDirectoryItems(handle, dir_items)

    xbmcplugin.endOfDirectory(handle, cacheToDisc=False)


def search_results(params):

    item_type = params.get('item_type')
    query_string = params.get('query')
    if query_string:
        log.debug(f"query_string : {query_string}")
        query_string = unquote(query_string)
        log.debug(f"query_string : {query_string}")

    item_type = item_type.lower()

    if item_type == 'movie':
        heading_type = translate_string(30231)
        content_type = 'movies'
    elif item_type == 'series':
        heading_type = translate_string(30229)
        content_type = 'tvshows'
    elif item_type == 'episode':
        heading_type = translate_string(30235)
        content_type = 'episodes'
        params["name_format"] = "Episode|episode_name_format"
    elif item_type in ["music", "audio", "musicalalbum"]:
        heading_type = 'Music'
        content_type = 'songs'
    elif item_type == "person":
        heading_type = 'Artists'
        content_type = 'artists'
    else:
        heading_type = item_type
        content_type = 'video'

    handle = int(sys.argv[1])

    if not query_string:
        home_window = HomeWindow()
        last_search = home_window.get_property("last_search")
        kb = xbmc.Keyboard()
        kb.setHeading(f"{heading_type.capitalize()} {translate_string(30246).lower()}")
        kb.setDefault(last_search)
        kb.doModal()

        if kb.isConfirmed():
            user_input = kb.getText().strip()
        else:
            return

        home_window.set_property("last_search", user_input)
        log.debug(f'searchResults Called: {params}')
        query = user_input

    else:
        query = query_string

    query = quote(query)
    log.debug(f"query : {query}")

    if (not item_type) or (not query):
        return

    # show a progress indicator if needed
    settings = xbmcaddon.Addon()
    progress = None
    if settings.getSetting('showLoadProgress') == "true":
        progress = xbmcgui.DialogProgress()
        progress.create(translate_string(30112))
        progress.update(0, translate_string(30113))

    # what type of search
    if item_type == "person":
        url_path = "/Persons"
        url_params = {
            "searchTerm": query,
            "IncludePeople": True,
            "IncludeMedia": False,
            "IncludeGenres": False,
            "IncludeStudios": False,
            "IncludeArtists": False,
            "Limit": 16,
            "Fields": "PrimaryImageAspectRatio,BasicSyncInfo,ProductionYear",
            "Recursive": True,
            "EnableTotalRecordCount": False,
            "ImageTypeLimit": 1,
            "userId": api.user_id
        }

        search_url = get_jellyfin_url(url_path, url_params)

        person_search_results = api.get(search_url)
        log.debug(f"Person Search Result : {person_search_results}")
        if person_search_results is None:
            return

        person_items = person_search_results.get("Items", [])

        server = settings.getSetting('server_address')
        list_items = []
        for item in person_items:
            person_id = item.get('Id')
            person_name = item.get('Name')
            person_thumbnail = get_art_url(item, "Primary", server=server)

            action_url = f"{addon_id}?mode=NEW_SEARCH_PERSON&person_id={person_id}"

            list_item = xbmcgui.ListItem(label=person_name, offscreen=True)
            list_item.setProperty("id", person_id)

            art_links = {}
            art_links["icon"] = "DefaultActor.png"
            if person_thumbnail:
                art_links["thumb"] = person_thumbnail
                art_links["poster"] = person_thumbnail
            list_item.setArt(art_links)

            item_tuple = (action_url, list_item, True)
            list_items.append(item_tuple)

        xbmcplugin.setContent(handle, 'artists')
        xbmcplugin.addDirectoryItems(handle, list_items)
        xbmcplugin.endOfDirectory(handle, cacheToDisc=False)

    else:
        url_path = f"/Users/{api.user_id}/Items"
        url_params = {
            "searchTerm": query,
            "IncludePeople": False,
            "IncludeMedia": True,
            "IncludeGenres": False,
            "IncludeStudios": False,
            "IncludeArtists": False,
            "IncludeItemTypes": item_type,
            "Limit": 16,
            "Fields": get_default_filters(),
            "Recursive": True,
            "EnableTotalRecordCount": False,
            "ImageTypeLimit": 1
        }

        search_url = get_jellyfin_url(url_path, url_params)

        # set content type
        xbmcplugin.setContent(handle, content_type)
        dir_items, detected_type, total_records = process_directory(
            search_url, progress, params
        )
        xbmcplugin.addDirectoryItems(handle, dir_items)
        xbmcplugin.endOfDirectory(handle, cacheToDisc=False)

    if progress is not None:
        progress.update(100, translate_string(30125))
        progress.close()


def play_action(params):
    log.debug("== ENTER: PLAY ==")

    log.debug(f"PLAY ACTION PARAMS: {params}")
    item_id = params.get("item_id")

    auto_resume = params.get("auto_resume", "-1")
    if auto_resume == 'None':
        auto_resume = '-1'
    if auto_resume:
        auto_resume = int(auto_resume)
    else:
        auto_resume = -1

    log.debug(f"AUTO_RESUME: {auto_resume}")

    force_transcode = params.get("force_transcode", None) is not None
    log.debug(f"FORCE_TRANSCODE: {force_transcode}")

    media_source_id = params.get("media_source_id", "")
    log.debug(f"media_source_id: {media_source_id}")

    subtitle_stream_index = params.get("subtitle_stream_index")
    log.debug(f"subtitle_stream_index: {subtitle_stream_index}")

    audio_stream_index = params.get("audio_stream_index")
    log.debug(f"audio_stream_index: {audio_stream_index}")

    action = params.get("action", "play")

    # set the current playing item id
    # set all the playback info, this will be picked up by the service
    # the service will then start the playback

    xbmc.Player().stop()

    play_info = {}
    play_info["action"] = action
    play_info["item_id"] = item_id
    play_info["auto_resume"] = str(auto_resume)
    play_info["force_transcode"] = force_transcode
    play_info["media_source_id"] = media_source_id
    play_info["subtitle_stream_index"] = subtitle_stream_index
    play_info["audio_stream_index"] = audio_stream_index
    log.info(f"Sending jellycon_play_action : {play_info}")
    play_file(play_info)


def play_item_trailer(item_id):
    log.debug("== ENTER: playTrailer ==")
    handle = int(sys.argv[1]) if sys.argv and len(sys.argv) > 1 else -1
    if handle != -1:
        xbmcplugin.endOfDirectory(handle, succeeded=False, updateListing=False, cacheToDisc=False)
        
    url = "/Users/{}/Items/{}/LocalTrailers?format=json".format(
        user_details.get('user_id'), item_id
    )

    result = api.get(url)

    if result is None:
        return

    log.debug(f"LocalTrailers {result}")
    count = 1

    trailer_names = []
    trailer_list = []
    for trailer in result:
        info = {}
        info["type"] = "local"
        name = trailer.get("Name")
        while not name or name in trailer_names:
            name = f"Trailer {count}"
            count += 1
        info["name"] = name
        info["id"] = trailer.get("Id")
        count += 1
        trailer_names.append(name)
        trailer_list.append(info)

    url = "/Users/{}/Items/{}?format=json&Fields=RemoteTrailers".format(
        user_details.get("user_id"), item_id
    )
    result = api.get(url)
    log.debug(f"RemoteTrailers: {result}")
    count = 1

    if result is None:
        return

    remote_trailers = result.get("RemoteTrailers", [])
    for trailer in remote_trailers:
        info = {}
        info["type"] = "remote"
        url = trailer.get("Url", "none")
        if url.lower().find("youtube") != -1:
            info["url"] = url
            name = trailer.get("Name")
            while not name or name in trailer_names:
                name = f"Trailer {count}"
                count += 1
            info["name"] = name
            trailer_names.append(name)
            trailer_list.append(info)

    log.debug(f"TrailerList: {trailer_list}")

    trailer_text = []
    for trailer in trailer_list:
        name = f"{trailer.get('name')} ({trailer.get('type')})"
        trailer_text.append(name)

    dialog = xbmcgui.Dialog()
    resp = dialog.select(translate_string(30308), trailer_text)
    if resp > -1:
        trailer = trailer_list[resp]
        log.debug(f"SelectedTrailer: {trailer}")

        if trailer.get("type") == "local":
            params = {}
            params["item_id"] = trailer.get("id")
            play_action(params)

        elif trailer.get("type") == "remote":
            youtube_id = trailer.get("url").rsplit('=', 1)[1]
            url_root = "plugin.video.youtube/play/?video_id="
            play_url = f"PlayMedia(plugin://{url_root}{youtube_id})"
            log.debug(f"youtube_plugin: {play_url}")

            xbmc.executebuiltin(play_url)
