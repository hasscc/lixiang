# LiXiang Auto for HomeAssistant

<a name="install"></a>
## 安装/更新

#### 方法1: 通过`Samba`或`SFTP`手动安装
> 下载并复制`custom_components/lixiang`文件夹到HA根目录下的`custom_components`文件夹

#### 方法2: 通过`SSH`或`Terminal & SSH`加载项执行一键安装命令
```shell
wget -O - https://ghproxy.com/raw.githubusercontent.com/hasscc/get/main/get | HUB_DOMAIN=ghproxy.com/github.com DOMAIN=lixiang REPO_PATH=hasscc/lixiang ARCHIVE_TAG=main bash -
```


<a name="config"></a>
## 配置

> [⚙️ 配置](https://my.home-assistant.io/redirect/config) > 设备与服务 > [🧩 集成](https://my.home-assistant.io/redirect/integrations) > [➕ 添加集成](https://my.home-assistant.io/redirect/config_flow_start?domain=lixiang) > 🔍 搜索 `理想汽车`

或者点击: [![添加集成](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start?domain=lixiang)

### 获取Token/Sign等配置选项
- 安卓模拟器抓包获取
  - [网易MuMu模拟器](https://mumu.163.com/mac/index.html) (安卓6.0)
  - [理想汽车APP v5.11.0](https://www.wandoujia.com/apps/7954884/history_v1030) (v5.12以上需要安卓7.0)
  - 注册一个理想APP小号
  - 在车机中控屏上扫码登陆小号
  - 在模拟器中安装理想汽车APP并登陆主账号(非小号)
  - 通过Charles/Fiddler等工具抓包
  - 筛选`ssp-as-mobile-api`相关的请求
  - 获取请求头信息中的`x-chj-key`、`x-chj-sign`和`x-chj-deviceid`
  - 在模拟器中的理想汽车APP并登陆小号
  - 抓包获取请求头信息中的`x-chj-token` (`APP-`开头)
  - 小号登陆APP是看不到车辆的，因此通过小号接入的车辆在HA中无法控制空调和寻车，仅可查看状态
  - 理想不允许同一账号登陆多设备，需要控制空调等需要自己想办法抓取主账号的token
