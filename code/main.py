import json
import os.path
import random

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse
import httpx
import loguru
from PIL import Image

from nonebot import logger


def _log_patcher(record: "loguru.Record"):
    module_name = record["name"]
    record["name"] = module_name and module_name.split(".")[0]


log_level = "DEBUG"
logger.configure(extra={"nonebot_log_level": log_level}, patcher=_log_patcher)

base_path = "."
eagle_cache = f"{base_path}/cache"
eagle_url = "http://127.0.0.1:41595"
eagle_db_data = {
    "token": "9434ca08-fa1e-4e31-a79d-3b9f984da0eb",
    "images": {}
}


def eagle_api(path: str, params=None):
    if params is None:
        params = {}
    if not path.startswith("/"):
        path = "/" + path
    params["token"] = eagle_db_data["token"]
    logger.debug(f"请求eagle_api:{path}, params:{params}")
    data = httpx.get(f"{eagle_url}{path}", params=params).content
    json_data = json.loads(data)
    if json_data["status"] != "success":
        logger.error(f"api请求错误{path}")
        logger.error(json_data)
        raise "api请求错误"
    return json_data["data"]


eagle_db_data["file_path"] = eagle_api("/api/library/info")["library"]["path"]
app = FastAPI()


@app.get("/")
async def eagle_web(order_by: str = None, folders: str = None):
    file = open(f"{base_path}/file/main.html", "r", encoding="UTF-8")
    html_file = file.read()
    file.close()
    reverse = False
    if order_by is not None:
        reverse = True if order_by.startswith("-") else False
        order_by = order_by.removeprefix("-")

    # ## 资源库列表 ##
    # 资源库名称
    library_data = eagle_api("/api/library/info")
    library_html = ('<a href="#" class="library">'
                    '<img src="api/self_image/icon.png" alt="Sidebar Image" style="width: 30px; height: auto;">'
                    f'{library_data["library"]["name"]}</a>')

    # 资源库列表（eagle_api失效）
    # library_list = []
    # library_html += '<ul class="submenu">'
    # for library in library_list:
    #     library_html += f'<li><a href="#">{library["name"]}</a></li>'
    # library_html += '</ul>'
    html_file = html_file.replace("<!-- replace -library- replace -->", library_html)

    # ## 默认文件夹 ##
    default_folders = {
        "全部": {
            "url": "/",
            "icon": "api/self_image/icon_all.png"
        },
        "最近修改": {
            "url": "/?order_by=change_date",
            "icon": "api/self_image/icon_new_use.png"
        },
        "最近添加": {
            "url": "/?order_by=add_date",
            "icon": "api/self_image/icon_new_add.png"
        },
        "随机模式": {
            "url": "/?order_by=random",
            "icon": "api/self_image/icon_random.png"
        },
        "上传": {
            "url": "/upload",
            "icon": "api/self_image/icon_upload.png"
        },
    }
    if folders is not None:
        default_folders["上传"]["url"] += f"?folders={folders}"
    default_folder_html = ""
    for folder in default_folders.keys():
        default_folder_html += (
            f'<a href="{default_folders[folder]["url"]}" class="folder">'
            f'<img src="{default_folders[folder]["icon"]}" alt="{folder}" style="width: 20px; height: auto;">'
            f'{folder}'
            f'</a>')

    html_file = html_file.replace("<!-- replace -default_folder- replace -->", default_folder_html)

    # ## 文件夹列表 ##
    def folder_list_to_html(folder_list: list, is_children: bool = False, tier: int = 0):
        to_html = ""
        tier_text = ""
        # 层级标识
        # for i in range(tier):
        #     tier_text += "| "
        if is_children is True:
            if len(folder_list) != 0:
                to_html += '<a href="#" class="toggler">-----展开</a><ul class="submenu">'
            for folder in folder_list:
                to_html += (
                    f'<a href="/?folders={folder["id"]}">'
                    f'{tier_text + folder["name"]}'
                    f'<p class="folder-number">{folder["imageCount"]}</p></a>')
                to_html += folder_list_to_html(folder["children"], is_children=True, tier=tier + 1)
            if len(folder_list) != 0:
                to_html += '</ul>'
        else:
            for folder in folder_list:
                to_html += (f'<a href="/?folders={folder["id"]}" '
                            f'class="{"folder_self" if folders == folder["id"] else "folder"}">'
                            f'<img src="api/self_image/icon_folder.png" '
                            f'alt="Sidebar Image" style="width: 20px; height: auto;">'
                            f'{tier_text + folder["name"]}'
                            f'<p class="folder-number">'
                            f'{folder["imageCount"]}'
                            f'</p>'
                            f'</a>')
                to_html += folder_list_to_html(folder["children"], is_children=True, tier=tier + 1)
        return to_html

    folder_list = eagle_api("/api/folder/list")
    folder_html = folder_list_to_html(folder_list)
    html_file = html_file.replace("<!-- replace -folder- replace -->", folder_html)

    # ## 排序标签 ##
    navbar_html = ""
    navbar_list = {
        "add_date": "添加日期",
        "change_date": "修改日期",
        "create_date": "创建日期",
        "file_size": "文件大小",
        "image_h": "图片高",
        "image_w": "图片宽",
        "name": "名称",
        "random": "随机",
    }
    for sort_name in navbar_list.keys():
        if order_by is not None and order_by == sort_name and sort_name != "random":
            if reverse is True:
                navbar_html += f'<a href="/?order_by={sort_name}">{navbar_list[sort_name]} ▼</a>'
            else:
                navbar_html += f'<a href="/?order_by=-{sort_name}">{navbar_list[sort_name]} ▲</a>'
        else:
            navbar_html += f'<a href="/?order_by={sort_name}">{navbar_list[sort_name]}</a>'
    html_file = html_file.replace("<!-- replace -navbar- replace -->", navbar_html)

    # ## 图片 ##
    images_html = ""
    params = {}
    if folders is not None:
        item_list: list = eagle_api("/api/item/list", {"folders": folders})
    else:
        item_list: list = eagle_api("/api/item/list")

    # 筛选文件夹
    item_list2 = []
    for item in item_list:
        if item["isDeleted"] is True:
            continue
        item_list2.append(item)

    item_list = item_list2

    # 排序
    if order_by is not None:
        sort_name = {
            "add_date": "modificationTime",  # 添加日期
            "change_date": "mtime",  # 修改日期
            "create_date": "btime",  # 创建日期
            "file_size": "btime",  # 文件大小
            "image_h": "height",  # 尺寸h
            "image_w": "width",  # 尺寸w
        }
        # 其他排序方式["name", "random"]
        # 计算排序
        if order_by in sort_name.keys():
            # 获取列表
            sort_list = []
            for data in item_list:
                if data[sort_name[order_by]] not in sort_list:
                    sort_list.append(data[sort_name[order_by]])

            # 排序
            sort_list2 = []
            while len(sort_list) > 0:
                max_ = max(sort_list)
                sort_list2.append(max_)
                sort_list.remove(max_)

            # 按排序组装
            item_list2 = []
            for sort in sort_list2:
                for item in item_list:
                    if item[sort_name[order_by]] == sort:
                        item_list2.append(item)
            item_list = item_list2
        elif order_by == "name":
            # 获取列表
            sort_list = []
            for data in item_list:
                if data["name"] not in sort_list:
                    sort_list.append(data["name"])

            # 排序
            sort_list.sort()

            # 按排序组装
            item_list2 = []
            for sort in sort_list:
                for item in item_list:
                    if item["name"] == sort:
                        item_list2.append(item)
            item_list = item_list2
        elif order_by == "random":
            item_list2 = []
            while len(item_list) > 0:
                choose = random.choice(item_list)
                item_list2.append(choose)
                item_list.remove(choose)
            item_list = item_list2

        # 倒序
        if reverse is True:
            num = len(item_list)
            item_list2 = []
            while num > 0:
                num -= 1
                item_list2.append(item_list[num])
            item_list = item_list2

    # 组装图片html
    for data in item_list:
        if data["isDeleted"] is True:
            continue
        images_html += (f'<img src="/api/image/preview?image_id={data["id"]}&amp;'
                        f'image_name={data["name"]}.{data["ext"]}" alt="{data["name"]}" '
                        f'style="margin: 3px;">')

    html_file = html_file.replace("<!-- replace -images- replace -->", images_html)

    return HTMLResponse(html_file)


@app.post("/upload_image")
async def upload_files(files: list[UploadFile] = File(...), folders: str = None):
    if folders is not None:
        logger.debug(f"上传至文件夹{folders}")
    upload_data = {
        "items": [],
        "folderId": folders,
        "token": eagle_db_data["token"]
    }
    upload_path = os.path.abspath('.') + "/cache/upload_cache"
    os.makedirs(upload_path, exist_ok=True)
    num = 0
    for file in files:
        num += 1
        file_content = await file.read()
        file_name = f"upload_{num}_{file.filename}.png"
        file_path = f"{upload_path}/{file_name}"
        with open(file_path, "wb") as image:
            image.write(file_content)
        upload_data["items"].append({
            "name": file_name,
            "path": file_path
        })
    logger.debug(f"上传图片信息：{upload_data}")
    url = f"{eagle_url}/api/item/addFromPaths"
    data = httpx.post(url, json=upload_data).content
    if json.loads(data)["status"] == "success":
        logger.success("上传成功")
    else:
        logger.error("上传失败")
        logger.error(data)
    for image_data in upload_data["items"]:
        os.remove(image_data["path"])
    # eagle貌似没有提供相同图片处理办法，只能在客户端解决是否保存相同图片。
    return {"status": "success"}


@app.get("/upload")
async def eagle_web(folders: str = None):
    file = open(f"{base_path}/file/main.html", "r", encoding="UTF-8")
    html_file = file.read()
    file.close()

    # ## 资源库列表 ##
    # 资源库名称
    library_data = eagle_api("/api/library/info")
    library_html = ('<a href="#" class="library">'
                    '<img src="api/self_image/icon.png" alt="Sidebar Image" style="width: 30px; height: auto;">'
                    f'{library_data["library"]["name"]}</a>')

    # 资源库列表（eagle_api失效）
    # library_list = []
    # library_html += '<ul class="submenu">'
    # for library in library_list:
    #     library_html += f'<li><a href="#">{library["name"]}</a></li>'
    # library_html += '</ul>'
    html_file = html_file.replace("<!-- replace -library- replace -->", library_html)

    # ## 默认文件夹 ##
    default_folders = {
        "返回资源库": {
            "url": "/",
            "icon": "api/self_image/icon_all.png"
        },
    }
    if folders is not None:
        default_folders["返回资源库"]["url"] += f"?folders={folders}"

    default_folder_html = ""
    for folder in default_folders.keys():
        default_folder_html += (f'<a href="{default_folders[folder]["url"]}" class="folder">'
                                f'<img src="{default_folders[folder]["icon"]}" alt="{folder}" '
                                f'style="width: 20px; height: auto;">{folder}</a>')

    html_file = html_file.replace("<!-- replace -default_folder- replace -->", default_folder_html)

    # ## 文件夹列表 ##
    def folder_list_to_html(folder_list: list, is_children: bool = False, tier: int = 0):
        to_html = ""
        tier_text = ""
        # 层级标识
        # for i in range(tier):
        #     tier_text += "| "
        if is_children is True:
            if len(folder_list) != 0:
                to_html += '<a href="#" class="toggler">-----展开</a><ul class="submenu">'
            for folder in folder_list:
                to_html += f'<a href="/upload?folders={folder["id"]}">{tier_text + folder["name"]}</a>'
                to_html += folder_list_to_html(folder["children"], is_children=True, tier=tier + 1)
            if len(folder_list) != 0:
                to_html += '</ul>'
        else:
            for folder in folder_list:
                to_html += (f'<a href="/upload?folders={folder["id"]}" class="folder">'
                            f'<img src="api/self_image/icon_folder.png" '
                            f'alt="Sidebar Image" style="width: 20px; height: auto;">'
                            f'{tier_text + folder["name"]}</a>')
                to_html += folder_list_to_html(folder["children"], is_children=True, tier=tier + 1)
        return to_html

    folder_list = eagle_api("/api/folder/list")
    folder_html = folder_list_to_html(folder_list)
    html_file = html_file.replace("<!-- replace -folder- replace -->", folder_html)

    # ## 排序标签 ##
    navbar_html = ""
    html_file = html_file.replace("<!-- replace -navbar- replace -->", navbar_html)

    # ## 上传 ##
    def folder_list_to_path(folder_list: list, folder_id: str):
        for folder in folder_list:
            if folder_id == folder["id"]:
                return folder['name']
            if len(folder['children']) > 0:
                path = folder_list_to_path(folder['children'], folder_id)
                if path:
                    return folder['name'] + '/' + path
        return None

    upload_html = ""
    folder_path = f"/{folder_list_to_path(folder_list, folders)}"
    upload_html += f"<p>上传至文件夹：{folders}</p>"
    upload_html += f"<p>路径：{folder_path}</p>"

    upload_html += (
        '<input type="file" id="fileInput" accept="image/*" style="display: none;" onchange="uploadImage()" multiple>')
    upload_html += (
            '<button class="upload-btn" onclick="document.getElementById(' + "'fileInput'" + ').click()">上传图片</button>')
    upload_url = f"/upload_image"
    if folders is not None:
        upload_url += f"?folders={folders}"

    html_file = html_file.replace("<!-- replace -images_upload_url- replace -->", upload_url)
    html_file = html_file.replace("<!-- replace -images- replace -->", upload_html)

    return HTMLResponse(html_file)


@app.get("/api/eagle")
async def eagle_web(path: str, **params):
    try:
        data = eagle_api(path, params)
        return {"status": "success", "data": data}
    except Exception as e:
        return {"status": "error", "message": e, "data": ""}


@app.get("/api/self_image/{image_name}")
async def eagle_web(image_name: str):
    if os.path.exists(f"{base_path}/file/{image_name}"):
        return FileResponse(f"{base_path}/file/{image_name}")
    raise "图片不存在"


@app.get("/api/image/{image_type}")
async def eagle_web(image_type: str, image_id: str, image_name: str):
    eagle_path = eagle_db_data["file_path"]

    if not os.path.exists(f"{eagle_path}/images"):
        logger.error(f"不存在此库{eagle_path}")
        return {"code": 1, "message": "不存在此库", "data": ""}
    if not os.path.exists(f"{eagle_path}/images/{image_id}.info"):
        logger.error(f"不存在此图片{image_id}")
        return {"code": 1, "message": "不存在此图片", "data": ""}
    if not os.path.exists(f"{eagle_path}/images/{image_id}.info/{image_name}"):
        logger.error(f"不存在此图片文件{image_name}")
        return {"code": 1, "message": "不存在此图片文件", "data": ""}
    # if os.path.exists(f"{eagle_path}/images/{image_id}.info/{image_name.replace('.', '_thumbnail.')}"):
    #     return FileResponse(f"{eagle_path}/images/{image_id}.info/{image_name.replace('.', '_thumbnail.')}")
    if image_type == "image":
        return FileResponse(f"{eagle_path}/images/{image_id}.info/{image_name}")
    elif image_type == "preview":
        path = f"{eagle_cache}/{eagle_path.replace(':', '')}/"
        if not os.path.exists(path):
            os.makedirs(path)
        path += image_name
        if not os.path.exists(path):
            if os.path.exists(f"{eagle_path}/images/{image_id}.info/{image_name.replace('.', '_thumbnail.')}"):
                image = Image.open(f"{eagle_path}/images/{image_id}.info/{image_name.replace('.', '_thumbnail.')}")
            else:
                image = Image.open(f"{eagle_path}/images/{image_id}.info/{image_name}")
            w, h = image.size
            x = 150
            y = int(h * x / w)
            image = image.resize((x, y))
            image.save(path)
        return FileResponse(path)
    raise "none"
