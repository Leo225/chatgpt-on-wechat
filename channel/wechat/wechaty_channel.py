# encoding:utf-8

"""
wechaty channel
Python Wechaty - https://github.com/wechaty/python-wechaty
"""
import asyncio
import base64
import os
import time

from wechaty import Contact, Wechaty, Friendship, FriendshipType
from wechaty.user import Message
from wechaty_puppet import FileBox

from bridge.context import *
from bridge.context import Context
from bridge.reply import *
from channel.chat_channel import ChatChannel
from channel.wechat.wechaty_message import WechatyMessage
from common.log import logger
from common.singleton import singleton
from config import conf

try:
    from voice.audio_convert import any_to_sil
except Exception as e:
    pass


@singleton
class WechatyChannel(ChatChannel):
    NOT_SUPPORT_REPLYTYPE = []

    def __init__(self):
        super().__init__()

    def startup(self):
        config = conf()
        token = config.get("wechaty_puppet_service_token")
        os.environ["WECHATY_PUPPET_SERVICE_TOKEN"] = token
        asyncio.run(self.main())

    async def main(self):
        loop = asyncio.get_event_loop()
        # 将asyncio的loop传入处理线程
        self.handler_pool._initializer = lambda: asyncio.set_event_loop(loop)
        self.bot = Wechaty()
        self.bot.on("login", self.on_login)
        self.bot.on("friendship", self.on_friendship)
        self.bot.on("message", self.on_message)
        await self.bot.start()

    async def on_login(self, contact: Contact):
        self.user_id = contact.contact_id
        self.name = contact.name
        logger.info("[WX] login user={}".format(contact))

    async def on_friendship(self, friendship: Friendship):
        contact = friendship.contact()
        contact_card = self.bot.Contact.load("Da1Zh0nggu0")
        logger.info("[WX] friendship contact_card={}".format(contact_card))
        await contact.ready()
        if friendship.type() == FriendshipType.FRIENDSHIP_TYPE_RECEIVE:
            await friendship.accept()
            await asyncio.sleep(3)
            await contact.say('''你好呀～我是nova～是星言科技创始人戴中国先生的智能助理～ \n在这里，你可以尽情向我询问关于星言科技的一切或与我随意进行聊天与互动～ \n例如对我说“做一下自我介绍
吧～”或其他任何问题，我都尽我所能进行回答！\n当然，你也可以直接添加我们创始人的微信，申请成为新言科技【超新星对话云】首批种子用户！''')
            await contact.say(contact_card)

    # 统一的发送函数，每个Channel自行实现，根据reply的type字段发送不同类型的消息
    def send(self, reply: Reply, context: Context):
        receiver_id = context["receiver"]
        loop = asyncio.get_event_loop()
        if context["isgroup"]:
            receiver = asyncio.run_coroutine_threadsafe(self.bot.Room.find(receiver_id), loop).result()
        else:
            receiver = asyncio.run_coroutine_threadsafe(self.bot.Contact.find(receiver_id), loop).result()
        msg = None
        if reply.type == ReplyType.TEXT:
            msg = reply.content
            asyncio.run_coroutine_threadsafe(receiver.say(msg), loop).result()
            logger.info("[WX] sendMsg={}, receiver={}".format(reply, receiver))
        elif reply.type == ReplyType.ERROR or reply.type == ReplyType.INFO:
            msg = reply.content
            asyncio.run_coroutine_threadsafe(receiver.say(msg), loop).result()
            logger.info("[WX] sendMsg={}, receiver={}".format(reply, receiver))
        elif reply.type == ReplyType.VOICE:
            voiceLength = None
            file_path = reply.content
            sil_file = os.path.splitext(file_path)[0] + ".sil"
            voiceLength = int(any_to_sil(file_path, sil_file))
            if voiceLength >= 60000:
                voiceLength = 60000
                logger.info("[WX] voice too long, length={}, set to 60s".format(voiceLength))
            # 发送语音
            t = int(time.time())
            msg = FileBox.from_file(sil_file, name=str(t) + ".sil")
            if voiceLength is not None:
                msg.metadata["voiceLength"] = voiceLength
            asyncio.run_coroutine_threadsafe(receiver.say(msg), loop).result()
            try:
                os.remove(file_path)
                if sil_file != file_path:
                    os.remove(sil_file)
            except Exception as e:
                pass
            logger.info("[WX] sendVoice={}, receiver={}".format(reply.content, receiver))
        elif reply.type == ReplyType.IMAGE_URL:  # 从网络下载图片
            img_url = reply.content
            t = int(time.time())
            msg = FileBox.from_url(url=img_url, name=str(t) + ".png")
            asyncio.run_coroutine_threadsafe(receiver.say(msg), loop).result()
            logger.info("[WX] sendImage url={}, receiver={}".format(img_url, receiver))
        elif reply.type == ReplyType.IMAGE:  # 从文件读取图片
            image_storage = reply.content
            image_storage.seek(0)
            t = int(time.time())
            msg = FileBox.from_base64(base64.b64encode(image_storage.read()), str(t) + ".png")
            asyncio.run_coroutine_threadsafe(receiver.say(msg), loop).result()
            logger.info("[WX] sendImage, receiver={}".format(receiver))

    async def on_message(self, msg: Message):
        """
        listen for message event
        """
        try:
            cmsg = await WechatyMessage(msg)
        except NotImplementedError as e:
            logger.debug("[WX] {}".format(e))
            return
        except Exception as e:
            logger.exception("[WX] {}".format(e))
            return
        logger.debug("[WX] message:{}".format(cmsg))
        room = msg.room()  # 获取消息来自的群聊. 如果消息不是来自群聊, 则返回None
        isgroup = room is not None
        ctype = cmsg.ctype
        context = self._compose_context(ctype, cmsg.content, isgroup=isgroup, msg=cmsg)
        if context:
            logger.info("[WX] receiveMsg={}, context={}".format(cmsg, context))
            self.produce(context)
