# import os.path
# from typing import Tuple, Dict
#
# from src.managers.filemanager import fileSender
#
# if __name__ == "__main__":
#     import sys
#     sys.path.append(os.path.join("C:\\Users\\7862s\\Desktop\\remotezone"))
#
# from src.avails.textobject import DataWeaver
# from src.avails.fileobject import FiLe
#
# every_file: Dict[str, Tuple[FiLe]] = {}
#
# if __name__ == "__main__":
#     data = DataWeaver(header="", content=[
#         "C:\\Users\\7862s\\Desktop\\dslab4.docx",
#         # "C:\\Users\\7862s\\Downloads\\Telegram Desktop\\P_20220319_193645.jpg",
#         # "C:\\Users\\7862s\\Downloads\\CiscoPacketTracer_821_Windows_64bit.exe",
#         # "C:\\Users\\7862s\\Downloads\\bison-2.4.1-setup.exe",
#         # "C:\\Users\\7862s\\Downloads\\dataspell-2023.2.3.exe",
#         # "C:\\Users\\7862s\\Downloads\\SamsungDeXSetupWin.exe",
#         # "C:\\Users\\7862s\\Downloads\\Rainmeter-4.5.17.exe",
#         # "C:\\Users\\7862s\\Downloads\\jdk-20_windows-x64_bin.msi",
#         # "C:\\Users\\7862s\\Downloads\\OpenJDK17U-jdk_x64_windows_hotspot_17.0.7_7.msi",
#         "C:\\Users\\7862s\\Downloads\\tsetup-x64.4.8.3.exe",
#         # "D:\\Clips\\20240308_131433.mp4",
#         # "D:\\Clips\\20240308_131433.mp4",
#         # "D:\\Clips\\20240308_132539.mp4",
#         # "D:\\Clips\\20240308_132643.mp4",
#         # "D:\\Clips\\20240308_132742.mp4",
#         # "D:\\Clips\\20240308_132816.mp4",
#         # "D:\\Clips\\20240308_132838.mp4",
#         # "D:\\Clips\\20240308_132908.mp4",
#         # "D:\\Clips\\20240308_133024.mp4",
#         # "D:\\Clips\\20240308_133024.mp4",
#         # "D:\\Clips\\20240308_133024.mp4",
#         "D:\\Movies\\Dead pool 1.mkv",
#         "D:\\Movies\\Fifty.Shades.of.Grey.2015.UNRATED.BRRip.XviD-ETRG.avi",
#         "D:\\Movies\\K_G_F_Chapter_2.mkv",
#         "D:\\Movies\\Predestination.2014.720p.BluRay.x264.700MB-[Mkvking.com].mkv",
#         "D:\\Movies\\Transformers_Rise_of_the_Beasts_2023_1080p_WEBRip_x265_10bit_Telugu.mkv",
#         "D:\\Movies\\Fifty.Shades.of.Grey.2015.UNRATED.BRRip.XviD-ETRG.avi",
#         "D:\\Movies\\K_G_F_Chapter_2.mkv",
#         "D:\\Movies\\Predestination.2014.720p.BluRay.x264.700MB-[Mkvking.com].mkv",
#         "D:\\Movies\\Transformers_Rise_of_the_Beasts_2023_1080p_WEBRip_x265_10bit_Telugu.mkv",
#     ],
#         _id=""
#     )
#     s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
#     s.bind(("localhost",8000))
#     s.listen(1)
#     reciever_sock, _ = s.accept()
#     fileSender(data, reciever_sock)
#
# """
# ~ 2,241,524 KB # sending
# -------------------------------------------------
# 19/1           | 18/2
# -------------------------------------------------
# 6.43 files/s   | 9/9 [00:03<00:00,  2.81 files/s]
#                | 9/9 [00:03<00:00,  2.69 files/s]
# -------------------------------------------------
#
#
# ~6.89GB # sending
# ---------------------------------
# 13/1           | 13/2
# ---------------------------------
# 1.35 files/s   | 7/7 2.24 files/s
#                | 6/6 2.23 files/s
# ---------------------------------
#
# ~14GB #sending
# ----------------------------------
#  11/2
# ----------------------------------
#  5/5 [00:18<00:00,  3.60s/ files]
#  6/6 [00:32<00:00,  5.46s/ files]
# ----------------------------------
# """