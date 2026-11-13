# -*- coding: utf-8 -*-
"""Мост Android для BeeWare (Briefcase + Chaquopy).

В отличие от python-for-android здесь Java-классы берутся через `jclass`,
а Java-интерфейсы реализуются через `dynamic_proxy`. Всё обёрнуто в try/except:
если на конкретной прошивке что-то недоступно, Nika не падает, а честно говорит,
что не получилось.
"""

import os
import re
import subprocess
import threading
import time

from .base import Bridge, Contact, Res
from ..wifi_parse import find_password, parse_wifi_config, parse_wpa_supplicant

try:
    from java import dynamic_proxy, jclass
    _JAVA = True
except Exception:  # на компьютере java-моста нет
    _JAVA = False

    def jclass(name):
        raise ImportError("java-мост доступен только на Android")

    def dynamic_proxy(interface):
        def deco(cls):
            return cls
        return deco


WIFI_CONFIG_PATHS = [
    "/data/misc/apexdata/com.android.wifi/WifiConfigStore.xml",
    "/data/misc/wifi/WifiConfigStore.xml",
    "/data/misc/wifi/WifiConfigStore.xml.bak",
    "/data/misc/wifi/wpa_supplicant.conf",
    "/data/wifi/bcm_supp.conf",
]

REQ_PERMISSIONS = 0x4E4B


def _activity():
    """Текущая Activity: у Briefcase это MainActivity.singletonThis."""
    MainActivity = None
    try:
        MainActivity = jclass("org.beeware.android.MainActivity")
    except Exception:
        MainActivity = None
    if MainActivity is not None:
        for attribute in ("singletonThis", "singleton", "mActivity"):
            try:
                activity = getattr(MainActivity, attribute)
                if activity is not None:
                    return activity
            except Exception:
                continue
    try:
        import toga
        app = toga.App.app
        native = app._impl.native
        if native is not None:
            return native
    except Exception:
        pass
    return None


class AndroidBridge(Bridge):
    is_android = True
    platform_name = "android"
    can_call = True
    can_contacts = True
    can_apps = True
    can_wifi_passwords = True
    can_voice = True
    can_notify = True

    NOTIF_CHANNEL = "nika_messages_v2"
    NOTIF_ID = 4101
    ALARM_CHANNEL = "nika_alarm_v2"
    ALARM_ID = 4102

    def __init__(self):
        super().__init__()
        self._ok = _JAVA
        self._ctx = _activity() if _JAVA else None
        self._tts = None
        self._tts_ready = False
        self._tts_pending = None
        self._voice_female = False
        self._voice_tuned = False
        self._pitch_override = None
        self._rate_override = None
        self._listen_cb = None
        self._listener = None
        self._recognizer = None
        self._torch_id = None
        self._torch_on = False
        self._ringtone = None
        if _JAVA and self._ctx is not None:
            self._init_tts()

    # ------------------------------------------------------------------
    #  Служебное
    # ------------------------------------------------------------------
    @staticmethod
    def _emit(tag, message):
        try:
            print("[Nika/android] %s: %s" % (tag, message))
        except Exception:
            pass

    def ready(self):
        return bool(self._ok and self._ctx is not None)

    def info(self):
        model = ""
        version = ""
        try:
            Build = jclass("android.os.Build")
            model = "%s %s" % (Build.MANUFACTURER, Build.MODEL)
            version = "Android %s" % jclass("android.os.Build$VERSION").RELEASE
        except Exception:
            pass
        return {"platform": self.platform_name, "android": True,
                "model": model.strip(), "version": version}

    def _start(self, intent):
        try:
            Intent = jclass("android.content.Intent")
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        except Exception:
            pass
        self._ctx.startActivity(intent)

    def pixel_ratio(self):
        """Плотность экрана: 1 DIP = density физических пикселей."""
        try:
            metrics = self._ctx.getResources().getDisplayMetrics()
            return float(metrics.density)
        except Exception:
            return 1.0

    def prepare_window(self):
        """Клавиатура поджимает окно, а не закрывает строку ввода."""
        def apply():
            try:
                LayoutParams = jclass("android.view.WindowManager$LayoutParams")
                window = self._ctx.getWindow()
                window.setSoftInputMode(
                    LayoutParams.SOFT_INPUT_ADJUST_RESIZE |
                    LayoutParams.SOFT_INPUT_STATE_UNSPECIFIED)
            except Exception as exc:
                self._emit("soft_input", exc)
            try:
                # Android 15+ любит edge-to-edge: пусть окно учитывает панели
                self._ctx.getWindow().setDecorFitsSystemWindows(True)
            except Exception:
                pass
        if self._run_on_ui(apply):
            return Res(True, "")
        return Res(False, "")

    def apply_voice_profile(self, pitch, rate):
        """Запоминает и сразу применяет тон и скорость голоса."""
        try:
            self._pitch_override = max(0.8, min(1.8, float(pitch)))
            self._rate_override = max(0.7, min(1.3, float(rate)))
        except Exception:
            return Res(False, "")
        try:
            if self._tts is not None and self._tts_ready:
                self._tts.setPitch(self._pitch_override)
                self._tts.setSpeechRate(self._rate_override)
            return Res(True, "")
        except Exception as exc:
            self._emit("voice_profile", exc)
            return Res(False, "")

    # ------------------------------------------------------------------
    #  Ссылки, приложения, магазин
    # ------------------------------------------------------------------
    def open_url(self, url):
        try:
            from urllib.parse import quote
            safe_url = quote(url, safe=":/?&=#%+@!$'()*,;[]~")
            Intent = jclass("android.content.Intent")
            Uri = jclass("android.net.Uri")
            self._start(Intent(Intent.ACTION_VIEW, Uri.parse(safe_url)))
            return Res(True, "", url)
        except Exception as exc:
            return Res(False, "не смогла открыть ссылку: %s" % exc)

    def app_installed(self, package):
        if not package:
            return False
        try:
            self._ctx.getPackageManager().getPackageInfo(package, 0)
            return True
        except Exception:
            return False

    def installed_apps(self):
        cached = self.cached_apps()
        if cached is not None:
            return cached
        apps = []
        try:
            pm = self._ctx.getPackageManager()
            infos = pm.getInstalledApplications(0)
            count = infos.size() if infos is not None else 0
            for index in range(count):
                info = infos.get(index)
                try:
                    label = str(pm.getApplicationLabel(info))
                except Exception:
                    label = ""
                try:
                    package = str(info.packageName)
                except Exception:
                    package = ""
                if label and package:
                    apps.append((label, package))
        except Exception as exc:
            self._emit("apps", exc)
        self.touch_apps_cache(apps)
        return apps

    def launch_package(self, package):
        try:
            intent = self._ctx.getPackageManager().getLaunchIntentForPackage(package)
            if intent is None:
                return Res(False, "не установлено")
            self._start(intent)
            return Res(True)
        except Exception as exc:
            return Res(False, str(exc))

    def open_play_store(self, package):
        try:
            Intent = jclass("android.content.Intent")
            Uri = jclass("android.net.Uri")
            self._start(Intent(Intent.ACTION_VIEW,
                               Uri.parse("market://details?id=%s" % package)))
            return Res(True)
        except Exception:
            return self.open_url("https://play.google.com/store/apps/details?id=%s" % package)

    # ------------------------------------------------------------------
    #  Контакты и звонки
    # ------------------------------------------------------------------
    def contacts(self):
        cached = self.cached_contacts()
        if cached is not None:
            return cached
        if not self.has_permission("READ_CONTACTS"):
            return []
        result = []
        seen = set()
        try:
            Phone = jclass("android.provider.ContactsContract$CommonDataKinds$Phone")
            resolver = self._ctx.getContentResolver()
            cursor = resolver.query(Phone.CONTENT_URI, None, None, None, None)
            if cursor is not None:
                idx_name = cursor.getColumnIndex("display_name")
                idx_number = cursor.getColumnIndex("data1")
                while cursor.moveToNext():
                    name = cursor.getString(idx_name) if idx_name >= 0 else ""
                    number = cursor.getString(idx_number) if idx_number >= 0 else ""
                    name = (name or "").strip()
                    number = (number or "").strip()
                    if not number:
                        continue
                    digits = re.sub(r"\D", "", number)
                    key = (name.lower(), digits[-10:])
                    if key in seen:
                        continue
                    seen.add(key)
                    from .. import nlp
                    result.append(Contact(
                        name=name or number,
                        number=nlp.normalize_phone(number) or number,
                        raw_number=number))
                cursor.close()
        except Exception as exc:
            self._emit("contacts", exc)
        self.touch_contacts_cache(result)
        return result

    def dial(self, number, direct=False):
        if not number:
            return Res(False, "не поняла номер.")
        try:
            Intent = jclass("android.content.Intent")
            Uri = jclass("android.net.Uri")
            if direct and self.has_permission("CALL_PHONE"):
                try:
                    self._start(Intent(Intent.ACTION_CALL, Uri.parse("tel:" + number)))
                    return Res(True, "звоню")
                except Exception:
                    pass
            self._start(Intent(Intent.ACTION_DIAL, Uri.parse("tel:" + number)))
            return Res(True, "набираю")
        except Exception as exc:
            return Res(False, "не смогла открыть номеронабиратель: %s" % exc)

    def send_sms(self, number, text):
        try:
            Intent = jclass("android.content.Intent")
            Uri = jclass("android.net.Uri")
            intent = Intent(Intent.ACTION_SENDTO, Uri.parse("smsto:" + number))
            if text:
                intent.putExtra("sms_body", text)
            self._start(intent)
            return Res(True, "")
        except Exception as exc:
            return Res(False, "не смогла открыть сообщения: %s" % exc)

    # ------------------------------------------------------------------
    #  Медиа
    # ------------------------------------------------------------------
    def _media_uri(self, query, video=False):
        try:
            resolver = self._ctx.getContentResolver()
            if video:
                Media = jclass("android.provider.MediaStore$Video$Media")
            else:
                Media = jclass("android.provider.MediaStore$Audio$Media")
            collection = Media.EXTERNAL_CONTENT_URI
            cursor = resolver.query(collection, None, "_display_name LIKE ?",
                                    ["%" + query + "%"], None)
            if cursor is None or not cursor.moveToFirst():
                if cursor is not None:
                    cursor.close()
                return None, ""
            idx_id = cursor.getColumnIndex("_id")
            idx_title = cursor.getColumnIndex("_display_name")
            media_id = cursor.getLong(idx_id) if idx_id >= 0 else 0
            title = str(cursor.getString(idx_title)) if idx_title >= 0 else query
            cursor.close()
            ContentUris = jclass("android.content.ContentUris")
            return ContentUris.withAppendedId(collection, media_id), title
        except Exception as exc:
            self._emit("media", exc)
            return None, ""

    def play_media(self, query="", video=False):
        uri = None
        title = ""
        if query:
            uri, title = self._media_uri(query, video)
        if uri is not None:
            try:
                Intent = jclass("android.content.Intent")
                intent = Intent(Intent.ACTION_VIEW)
                intent.setDataAndType(uri, "video/*" if video else "audio/*")
                intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                self._start(intent)
                return Res(True, "включаю", {"source": "local", "title": title})
            except Exception as exc:
                self._emit("play_media", exc)

        search = "https://m.youtube.com/results?search_query=" + (query or "").replace(" ", "+")
        if not query:
            search = "https://m.youtube.com"
        if video or not query:
            if self.app_installed("com.google.android.youtube"):
                if self.launch_package("com.google.android.youtube").ok:
                    return Res(True, "открываю ютуб", {"source": "youtube"})
        if not query:
            music = "com.google.android.apps.youtube.music"
            if self.app_installed(music):
                if self.launch_package(music).ok:
                    return Res(True, "открываю ютуб мьюзик", {"source": "youtube-music"})
        opened = self.open_url(search)
        if opened.ok:
            return Res(True, "ищу в ютубе", {"source": "web", "query": query})
        return Res(False, "не нашла «%s» ни в памяти, ни в ютубе." % query)

    # ------------------------------------------------------------------
    #  Будильник, фонарик, батарея, звук, настройки
    # ------------------------------------------------------------------
    def set_alarm(self, hour, minute, label=""):
        try:
            AlarmClock = jclass("android.provider.AlarmClock")
            Intent = jclass("android.content.Intent")
            intent = Intent(AlarmClock.ACTION_SET_ALARM)
            intent.putExtra(AlarmClock.EXTRA_HOUR, int(hour))
            intent.putExtra(AlarmClock.EXTRA_MINUTES, int(minute))
            intent.putExtra(AlarmClock.EXTRA_SKIP_UI, False)
            if label:
                intent.putExtra(AlarmClock.EXTRA_MESSAGE, label)
            self._start(intent)
            return Res(True, "")
        except Exception as exc:
            return Res(False, "не смогла открыть будильник: %s" % exc)

    def torch(self, on):
        try:
            Context = jclass("android.content.Context")
            CameraManager = jclass("android.hardware.camera2.CameraManager")
            manager = self._ctx.getSystemService(Context.CAMERA_SERVICE)
            if self._torch_id is None:
                ids = manager.getCameraIdList()
                self._torch_id = ids[0] if ids is not None and len(ids) else None
            if not self._torch_id:
                return Res(False, "не нашла вспышку.")
            manager.setTorchMode(self._torch_id, bool(on))
            self._torch_on = bool(on)
            return Res(True, "")
        except Exception as exc:
            return Res(False, "фонарик не поддался: %s" % exc)

    def battery(self):
        try:
            Intent = jclass("android.content.Intent")
            IntentFilter = jclass("android.content.IntentFilter")
            sticky = self._ctx.registerReceiver(None, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
            if sticky is None:
                return {}
            level = sticky.getIntExtra("level", -1)
            scale = sticky.getIntExtra("scale", 100)
            status = sticky.getIntExtra("status", -1)
            plugged = sticky.getIntExtra("plugged", -1)
            if level < 0:
                return {}
            return {"percent": int(round(level * 100.0 / (scale or 100))),
                    "charging": status == 2 or plugged > 0}
        except Exception:
            return {}

    def volume(self, direction):
        try:
            Context = jclass("android.content.Context")
            AudioManager = jclass("android.media.AudioManager")
            manager = self._ctx.getSystemService(Context.AUDIO_SERVICE)
            if manager is None:
                return Res(False, "не нашла регулятор звука.")
            stream = AudioManager.STREAM_MUSIC
            if direction == "up":
                manager.adjustStreamVolume(stream, AudioManager.ADJUST_RAISE,
                                           AudioManager.FLAG_SHOW_UI)
            elif direction == "down":
                manager.adjustStreamVolume(stream, AudioManager.ADJUST_LOWER,
                                           AudioManager.FLAG_SHOW_UI)
            elif direction == "mute":
                manager.setStreamVolume(stream, 0, AudioManager.FLAG_SHOW_UI)
            elif direction == "max":
                manager.setStreamVolume(stream, manager.getStreamMaxVolume(stream),
                                        AudioManager.FLAG_SHOW_UI)
            level = int(manager.getStreamVolume(stream))
            top = int(manager.getStreamMaxVolume(stream)) or 1
            return Res(True, "%d%%" % int(round(level * 100.0 / top)))
        except Exception as exc:
            return Res(False, "звук не поддался: %s" % exc)

    def open_settings(self, page=""):
        try:
            Settings = jclass("android.provider.Settings")
            actions = {
                "wifi": "ACTION_WIFI_SETTINGS",
                "apps": "ACTION_APPLICATION_SETTINGS",
                "bluetooth": "ACTION_BLUETOOTH_SETTINGS",
                "display": "ACTION_DISPLAY_SETTINGS",
                "sound": "ACTION_SOUND_SETTINGS",
                "battery": "ACTION_BATTERY_SAVER_SETTINGS",
                "location": "ACTION_LOCATION_SOURCE_SETTINGS",
                "data": "ACTION_DATA_ROAMING_SETTINGS",
                "notification": "ACTION_NOTIFICATION_SETTINGS",
            }
            name = actions.get(page or "", "ACTION_SETTINGS")
            action = getattr(Settings, name, Settings.ACTION_SETTINGS)
            Intent = jclass("android.content.Intent")
            self._start(Intent(action))
            return Res(True, "")
        except Exception as exc:
            return Res(False, "не смогла открыть настройки: %s" % exc)

    # ------------------------------------------------------------------
    #  Уведомления, звуки и системная шапка
    # ------------------------------------------------------------------
    def _notification_manager(self):
        try:
            Context = jclass("android.content.Context")
            return self._ctx.getSystemService(Context.NOTIFICATION_SERVICE)
        except Exception:
            return None

    def _ensure_channels(self, manager):
        """Два канала: тихие сообщения и громкий «будильник» для таймера."""
        try:
            Build = jclass("android.os.Build$VERSION")
            if int(Build.SDK_INT) < 26:
                return
            Channel = jclass("android.app.NotificationChannel")
            RingtoneManager = jclass("android.media.RingtoneManager")
            AudioAttributes = jclass("android.media.AudioAttributes")

            quiet = Channel(self.NOTIF_CHANNEL, "Nika", 3)
            quiet.setDescription("Ответы, напоминания")
            quiet.enableVibration(True)
            manager.createNotificationChannel(quiet)

            loud = Channel(self.ALARM_CHANNEL, "Nika — таймер", 4)
            loud.setDescription("Таймер и будильник")
            loud.enableVibration(True)
            try:
                loud.setVibrationPattern([0, 350, 180, 350, 180, 500])
            except Exception:
                pass
            try:
                uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
                if uri is None:
                    uri = RingtoneManager.getDefaultUri(
                        RingtoneManager.TYPE_NOTIFICATION)
                attributes = (AudioAttributes.Builder()
                              .setUsage(AudioAttributes.USAGE_ALARM)
                              .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                              .build())
                loud.setSound(uri, attributes)
            except Exception:
                pass
            try:
                loud.setBypassDnd(True)
            except Exception:
                pass
            manager.createNotificationChannel(loud)
        except Exception as exc:
            self._emit("channels", exc)

    def _build_notification(self, title, text, urgent=False):
        Build = jclass("android.os.Build$VERSION")
        sdk = int(Build.SDK_INT)
        Notification = jclass("android.app.Notification")
        Builder = jclass("android.app.Notification$Builder")
        if sdk >= 26:
            channel = self.ALARM_CHANNEL if urgent else self.NOTIF_CHANNEL
            builder = Builder(self._ctx, channel)
        else:
            builder = Builder(self._ctx)
        icon = self._ctx.getApplicationInfo().icon
        builder.setContentTitle(str(title))
        builder.setContentText(str(text))
        builder.setSmallIcon(icon)
        builder.setAutoCancel(True)
        builder.setOnlyAlertOnce(False)
        try:
            builder.setWhen(int(time.time() * 1000))
        except Exception:
            pass
        if urgent:
            try:
                builder.setCategory(Notification.CATEGORY_ALARM)
                builder.setPriority(Notification.PRIORITY_MAX)
                builder.setDefaults(Notification.DEFAULT_ALL)
                builder.setVisibility(Notification.VISIBILITY_PUBLIC)
            except Exception:
                pass
        else:
            try:
                builder.setPriority(Notification.PRIORITY_DEFAULT)
            except Exception:
                pass
        return builder

    def notify(self, title, text):
        try:
            manager = self._notification_manager()
            if manager is None:
                return Res(False, "")
            Build = jclass("android.os.Build$VERSION")
            if int(Build.SDK_INT) >= 33 and not self.has_permission("POST_NOTIFICATIONS"):
                return Res(False, "нет разрешения на уведомления")
            self._ensure_channels(manager)
            manager.notify(self.NOTIF_ID,
                           self._build_notification(title, text).build())
            return Res(True, "")
        except Exception as exc:
            self._emit("notify", exc)
            return Res(False, str(exc))

    def notify_alarm(self, title, text):
        try:
            manager = self._notification_manager()
            if manager is None:
                return Res(False, "")
            Build = jclass("android.os.Build$VERSION")
            if int(Build.SDK_INT) >= 33 and not self.has_permission("POST_NOTIFICATIONS"):
                return Res(False, "нет разрешения на уведомления")
            self._ensure_channels(manager)
            manager.notify(self.ALARM_ID,
                           self._build_notification(title, text, urgent=True).build())
            return Res(True, "")
        except Exception as exc:
            self._emit("notify_alarm", exc)
            return Res(False, str(exc))

    def click(self):
        """Короткий системный клик — без мелодий и задержек."""
        try:
            Context = jclass("android.content.Context")
            AudioManager = jclass("android.media.AudioManager")
            manager = self._ctx.getSystemService(Context.AUDIO_SERVICE)
            if manager is None:
                return Res(False, "")
            manager.playSoundEffect(0, 0.35)  # SoundEffectConstants.CLICK
            return Res(True, "")
        except Exception:
            return Res(False, "")

    def alarm_sound(self):
        """Звенит будильником, пока не остановят (не дольше 8 секунд)."""
        try:
            self.stop_sound()
            RingtoneManager = jclass("android.media.RingtoneManager")
            AudioManager = jclass("android.media.AudioManager")
            uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
            if uri is None:
                uri = RingtoneManager.getDefaultUri(
                    RingtoneManager.TYPE_NOTIFICATION)
            ringtone = RingtoneManager.getRingtone(self._ctx, uri)
            ringtone.setStreamType(AudioManager.STREAM_ALARM)
            self._ringtone = ringtone
            ringtone.play()
            timer = threading.Timer(8.0, self.stop_sound)
            timer.daemon = True
            timer.start()
            return Res(True, "")
        except Exception as exc:
            self._emit("alarm_sound", exc)
            return Res(False, str(exc))

    def stop_sound(self):
        try:
            if self._ringtone is not None:
                self._ringtone.stop()
                self._ringtone = None
            return Res(True, "")
        except Exception:
            self._ringtone = None
            return Res(False, "")

    def hide_system_bars(self):
        """Прячет системную шапку с названием приложения."""
        def apply():
            hidden = False
            try:
                self._ctx.setTitle("")
                hidden = True
            except Exception:
                pass
            for getter in ("getSupportActionBar", "getActionBar"):
                try:
                    bar = getattr(self._ctx, getter)()
                    if bar is not None:
                        bar.hide()
                        hidden = True
                except Exception:
                    pass
            try:
                Color = jclass("android.graphics.Color")
                WindowManager = jclass("android.view.WindowManager$LayoutParams")
                window = self._ctx.getWindow()
                window.addFlags(WindowManager.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS)
                window.setStatusBarColor(Color.parseColor("#0d0d0f"))
                window.setNavigationBarColor(Color.parseColor("#0d0d0f"))
                # светлые иконки на тёмном статус-баре
                try:
                    window.getDecorView().setSystemUiVisibility(0)
                except Exception:
                    pass
                hidden = True
            except Exception:
                pass
            return hidden

        if self._run_on_ui(apply):
            return Res(True, "")
        return Res(bool(apply()), "")

    def vibrate(self, ms=40):
        try:
            Context = jclass("android.content.Context")
            vibrator = self._ctx.getSystemService(Context.VIBRATOR_SERVICE)
            if vibrator is None:
                return Res(False, "")
            Build = jclass("android.os.Build$VERSION")
            if int(Build.SDK_INT) >= 26:
                VibrationEffect = jclass("android.os.VibrationEffect")
                vibrator.vibrate(VibrationEffect.createOneShot(int(ms), -1))
            else:
                vibrator.vibrate(int(ms))
            return Res(True, "")
        except Exception:
            return Res(False, "")

    def toast(self, text):
        """Короткий тост — по нему видно, до какого шага дошёл запуск."""
        def show():
            try:
                Toast = jclass("android.widget.Toast")
                Toast.makeText(self._ctx, str(text), Toast.LENGTH_SHORT).show()
            except Exception as exc:
                self._emit("toast", exc)
        if self._run_on_ui(show):
            return Res(True, "")
        return Res(False, "")

    # ------------------------------------------------------------------
    #  Голос
    # ------------------------------------------------------------------
    def _init_tts(self):
        try:
            TextToSpeech = jclass("android.speech.tts.TextToSpeech")
            Listener = jclass("android.speech.tts.TextToSpeech$OnInitListener")

            class OnInit(dynamic_proxy(Listener)):
                def __init__(self, callback):
                    super().__init__()
                    self.callback = callback

                def onInit(self, status):
                    try:
                        self.callback(status == 0)
                    except Exception:
                        pass

            engine = None
            try:
                self._ctx.getPackageManager().getPackageInfo("com.google.android.tts", 0)
                engine = "com.google.android.tts"
            except Exception:
                engine = None
            if engine:
                try:
                    self._tts = TextToSpeech(self._ctx, OnInit(self._on_tts_ready), engine)
                except Exception:
                    self._tts = TextToSpeech(self._ctx, OnInit(self._on_tts_ready))
            else:
                self._tts = TextToSpeech(self._ctx, OnInit(self._on_tts_ready))
        except Exception as exc:
            self._emit("tts", exc)
            self._tts = None

    def _on_tts_ready(self, ok):
        self._tts_ready = bool(ok)
        if not ok or self._tts is None:
            return
        self._apply_language()
        try:
            AudioAttributes = jclass("android.media.AudioAttributes")
            attributes = (AudioAttributes.Builder()
                          .setUsage(AudioAttributes.USAGE_ASSISTANT)
                          .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                          .build())
            self._tts.setAudioAttributes(attributes)
        except Exception:
            pass
        self._configure_voice()
        # список голосов иногда приходит с задержкой — пробуем ещё раз позже
        try:
            timer = threading.Timer(1.5, self._retry_voice)
            timer.daemon = True
            timer.start()
        except Exception:
            pass
        pending = self._tts_pending
        self._tts_pending = None
        if pending:
            self.speak(pending)

    def _apply_language(self):
        """Ставит русский язык, пробуя пару вариантов локали."""
        Locale = None
        try:
            Locale = jclass("java.util.Locale")
        except Exception:
            return False
        for args in (("ru", "RU"), ("ru", None)):
            try:
                locale = Locale(args[0], args[1]) if args[1] else Locale(args[0])
                status = int(self._tts.setLanguage(locale))
                if status >= 0:      # LANG_MISSING_DATA = -1, LANG_NOT_SUPPORTED = -2
                    return True
            except Exception as exc:
                self._emit("tts_lang", exc)
        return False

    def _retry_voice(self):
        if self._voice_female:
            return
        try:
            self._configure_voice()
        except Exception:
            pass

    def _configure_voice(self):
        """Выбирает женский русский голос.

        Android не отдаёт пол голоса отдельным полем, поэтому смотрим на имя
        и признаки голоса, а если женского нет — поднимаем тон: мужской голос
        с pitch 1.4 звучит женственно, а «переводчик» из настроек по умолчанию
        так не звучит никогда.
        """
        if self._tts is None:
            return
        female_marks = (
            "female", "жен", "ruf", "rua", "wavenet-a", "wavenet-c",
            "standard-a", "standard-c", "neural-a", "neural-c", "zira",
            "alena", "alyona", "milena", "katya", "tatiana", "tatyana",
            "irina", "svetlana",
        )
        male_marks = (
            "male", "муж", "rur", "rud", "ru-m", "wavenet-b", "wavenet-d",
            "standard-b", "standard-d", "neural-b", "neural-d", "pavel",
            "dmitri", "dmitry", "yuri", "maxim",
        )
        candidates = []
        try:
            voices = self._tts.getVoices()
            iterator = voices.iterator() if voices is not None else None
            while iterator is not None and iterator.hasNext():
                voice = iterator.next()
                try:
                    language = str(voice.getLocale().getLanguage()).lower()
                except Exception:
                    continue
                if language != "ru":
                    continue
                name = ""
                try:
                    name = str(voice.getName()).lower()
                except Exception:
                    pass
                features = ""
                try:
                    feature_set = voice.getFeatures()
                    if feature_set is not None:
                        feature_iterator = feature_set.iterator()
                        while feature_iterator.hasNext():
                            features += str(feature_iterator.next()).lower() + " "
                except Exception:
                    pass
                haystack = name + " " + features
                female = ("female" in haystack) or ("жен" in haystack)
                male = (not female) and (("male" in haystack) or ("муж" in haystack))
                if not female and not male:
                    female = any(mark in name for mark in female_marks)
                    male = (not female) and any(mark in name for mark in male_marks)
                score = 0
                if female:
                    score += 40
                if male:
                    score -= 40
                if "ruf" in name:
                    score += 12
                if "rur" in name or "rud" in name:
                    score -= 12
                try:
                    if voice.isNetworkConnectionRequired():
                        score -= 2      # без интернета сетевой голос молчит
                    else:
                        score += 4
                except Exception:
                    pass
                if "notinstalled" in features.replace(" ", ""):
                    score -= 60
                candidates.append((score, name, voice))
        except Exception as exc:
            self._emit("voice_choice", exc)

        # пробуем голоса по убыванию «женственности», пока какой-нибудь не встанет
        candidates.sort(key=lambda item: item[0], reverse=True)
        applied = False
        best_score = -999
        for score, name, voice in candidates:
            try:
                self._tts.setVoice(voice)
                applied = True
                best_score = score
                self._emit("voice", "выбран %s (score %s)" % (name, score))
                break
            except Exception as exc:
                self._emit("voice_set", exc)

        # уверенный женский голос не задираем, иначе — поднимаем тон
        self._voice_female = applied and best_score >= 20
        pitch = self._pitch_override if self._pitch_override is not None else \
            (1.16 if self._voice_female else 1.45)
        rate = self._rate_override if self._rate_override is not None else 0.94
        try:
            self._tts.setPitch(pitch)
            self._tts.setSpeechRate(rate)
        except Exception:
            pass
        self._voice_tuned = True

    def speak(self, text):
        if not text:
            return Res(False, "")
        if self._tts is None or not self._tts_ready:
            self._tts_pending = text
            return Res(False, "")
        try:
            if not self._voice_tuned:
                self._configure_voice()
            self._tts.speak(text, 0, None, "nika-%d" % int(time.time() * 1000))
            return Res(True, "")
        except Exception as exc:
            self._emit("speak", exc)
            return Res(False, "")

    def stop_speak(self):
        self._tts_pending = None
        try:
            if self._tts is not None:
                self._tts.stop()
            return Res(True, "")
        except Exception:
            return Res(False, "")

    def _run_on_ui(self, function):
        """Выполняет код в UI-потоке Android (нужно для SpeechRecognizer)."""
        try:
            Runnable = jclass("java.lang.Runnable")

            class Runner(dynamic_proxy(Runnable)):
                def __init__(self, fn):
                    super().__init__()
                    self.fn = fn

                def run(self):
                    try:
                        self.fn()
                    except Exception:
                        pass

            self._ctx.runOnUiThread(Runner(function))
            return True
        except Exception:
            try:
                function()
                return True
            except Exception as exc:
                self._emit("ui_thread", exc)
                return False

    def _make_listener(self, on_result, on_level=None, on_state=None,
                       on_partial=None):
        RecognitionListener = jclass("android.speech.RecognitionListener")

        def emit(callback, *args):
            if callback is None:
                return
            try:
                callback(*args)
            except Exception as exc:
                self._emit("stt_cb", exc)

        def first_match(results):
            try:
                matches = results.getStringArrayList("results_recognition")
                if matches is not None and matches.size() > 0:
                    return str(matches.get(0))
            except Exception:
                pass
            return ""

        class Listener(dynamic_proxy(RecognitionListener)):
            def onReadyForSpeech(self, params):
                emit(on_state, "ready")

            def onBeginningOfSpeech(self):
                emit(on_state, "speech")

            def onRmsChanged(self, rms):
                emit(on_level, rms)

            def onBufferReceived(self, buffer):
                pass

            def onEndOfSpeech(self):
                emit(on_state, "end")

            def onError(self, error):
                emit(on_state, "error")
                emit(on_result, None)

            def onResults(self, results):
                emit(on_result, first_match(results))

            def onPartialResults(self, results):
                text = first_match(results)
                if text:
                    emit(on_partial, text)

            def onEvent(self, event_type, params):
                pass

        return Listener()

    def listen(self, callback, on_level=None, on_state=None, on_partial=None):
        if not self.has_permission("RECORD_AUDIO"):
            def after_grant(ok):
                if ok:
                    self.listen(callback, on_level, on_state, on_partial)
                else:
                    if on_state is not None:
                        try:
                            on_state("denied")
                        except Exception:
                            pass
                    callback(None)
            self.request_permissions(["RECORD_AUDIO"], after_grant)
            return Res(True, "")

        try:
            RecognizerIntent = jclass("android.speech.RecognizerIntent")
            SpeechRecognizer = jclass("android.speech.SpeechRecognizer")
            Intent = jclass("android.content.Intent")

            try:
                if not SpeechRecognizer.isRecognitionAvailable(self._ctx):
                    return Res(False, "на телефоне нет службы распознавания речи.")
            except Exception:
                pass

            intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                            RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "ru-RU")
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, "ru-RU")
            intent.putExtra(RecognizerIntent.EXTRA_PROMPT, "Говори, я слушаю")
            intent.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
            if on_partial is not None:
                intent.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, True)

            listener = self._make_listener(callback, on_level, on_state, on_partial)

            def start():
                # SpeechRecognizer положено создавать и запускать в UI-потоке
                self._destroy_recognizer()
                self._recognizer = SpeechRecognizer.createSpeechRecognizer(self._ctx)
                self._recognizer.setRecognitionListener(listener)
                self._recognizer.startListening(intent)

            self._listener = listener
            if not self._run_on_ui(start):
                return Res(False, "не смогла запустить микрофон.")
            return Res(True, "")
        except Exception as exc:
            self._emit("listen", exc)
            return Res(False, "не смогла включить микрофон: %s" % exc)

    def _destroy_recognizer(self):
        recognizer = self._recognizer
        self._recognizer = None
        if recognizer is None:
            return
        for method in ("cancel", "destroy"):
            try:
                getattr(recognizer, method)()
            except Exception:
                pass

    def stop_listen(self):
        def stop():
            self._destroy_recognizer()
        if self._run_on_ui(stop):
            return Res(True, "")
        return Res(False, "")

    # ------------------------------------------------------------------
    #  Wi-Fi
    # ------------------------------------------------------------------
    def _wifi_manager(self):
        try:
            Context = jclass("android.content.Context")
            return self._ctx.getApplicationContext().getSystemService(Context.WIFI_SERVICE)
        except Exception:
            return None

    def wifi_saved(self):
        manager = self._wifi_manager()
        if manager is None:
            return []
        names = []
        try:
            networks = manager.getConfiguredNetworks()
            if networks is None:
                return []
            for index in range(networks.size()):
                network = networks.get(index)
                ssid = str(network.SSID or "").strip().strip('"')
                if ssid and ssid not in names:
                    names.append(ssid)
        except Exception as exc:
            self._emit("wifi_saved", exc)
        return names

    def wifi_info(self):
        manager = self._wifi_manager()
        info = {}
        if manager is None:
            return info
        try:
            current = manager.getConnectionInfo()
            if current is not None:
                ssid = str(current.getSSID() or "").strip().strip('"')
                if ssid and ssid not in ("<unknown ssid>", "0x", "unknown"):
                    info["ssid"] = ssid
                rssi = int(current.getRssi())
                if rssi < 0:
                    info["rssi"] = rssi
                ip_int = int(current.getIpAddress())
                if ip_int:
                    info["ip"] = "%d.%d.%d.%d" % (
                        ip_int & 0xFF, (ip_int >> 8) & 0xFF,
                        (ip_int >> 16) & 0xFF, (ip_int >> 24) & 0xFF)
        except Exception as exc:
            self._emit("wifi_info", exc)
        info["connected"] = bool(info.get("ssid"))
        saved = self.wifi_saved()
        if saved:
            info["saved"] = saved
        return info

    def _root_cat(self, path):
        commands = [
            ["su", "-c", "cat '%s'" % path],
            ["su", "-c", "cat %s" % path],
        ]
        for command in commands:
            try:
                proc = subprocess.run(command, capture_output=True, timeout=8)
                if proc.returncode == 0 and proc.stdout:
                    return proc.stdout.decode("utf-8", errors="replace")
            except Exception:
                continue
        try:
            with os.popen("su -c 'cat %s' 2>/dev/null" % path) as handle:
                data = handle.read()
            if data and "No such file" not in data:
                return data
        except Exception:
            pass
        return ""

    def _read_wifi_config(self):
        for path in WIFI_CONFIG_PATHS:
            text = self._root_cat(path)
            if text and ("<Network>" in text or "network={" in text
                         or "network = {" in text):
                return text, path
        return "", ""

    def wifi_password(self, ssid):
        text, path = self._read_wifi_config()
        if not text:
            return None, ""
        try:
            if path.endswith(".xml"):
                mapping = parse_wifi_config(text)
            else:
                mapping = parse_wpa_supplicant(text)
        except Exception:
            return None, ""
        password = find_password(mapping, ssid)
        if password:
            return password, "root"
        return None, ""

    # ------------------------------------------------------------------
    #  Права
    # ------------------------------------------------------------------
    def has_permission(self, name):
        try:
            Build = jclass("android.os.Build$VERSION")
            if int(Build.SDK_INT) < 23:
                return True
            full = name if name.startswith("android.permission.") else "android.permission." + name
            return int(self._ctx.checkSelfPermission(full)) == 0
        except Exception:
            return False

    def request_permissions(self, names, callback):
        try:
            Build = jclass("android.os.Build$VERSION")
            if int(Build.SDK_INT) < 23:
                callback(True)
                return Res(True, "")
            full = [n if n.startswith("android.permission.") else "android.permission." + n
                    for n in names]
            if all(self.has_permission(n) for n in names):
                callback(True)
                return Res(True, "")

            self._run_on_ui(lambda: self._ctx.requestPermissions(full, REQ_PERMISSIONS))

            def wait():
                deadline = time.time() + 120
                while time.time() < deadline:
                    if all(self.has_permission(n) for n in names):
                        callback(True)
                        return
                    time.sleep(0.25)
                callback(False)

            threading.Thread(target=wait, daemon=True).start()
            return Res(True, "")
        except Exception as exc:
            try:
                callback(False)
            except Exception:
                pass
            return Res(False, str(exc))
