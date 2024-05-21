from src.avails.fileobject import make_file_items, GROUP_MIN, _FileGroup

# FILE_NAME = 0
# FILE_SIZE = 1
# FILE_PATH = 2
# CONNECT_SENDER = 3
# CONNECT_RECEIVER = 4





if __name__ == "__main__":
    file_s = [
        "C:\\Users\\7862s\\Desktop\\dslab4.docx",
        "C:\\Users\\7862s\\Downloads\\Telegram Desktop\\P_20220319_193645.jpg",
        "C:\\Users\\7862s\\Downloads\\CiscoPacketTracer_821_Windows_64bit.exe",
        "C:\\Users\\7862s\\Downloads\\bison-2.4.1-setup.exe",
        "C:\\Users\\7862s\\Downloads\\dataspell-2023.2.3.exe",
        "C:\\Users\\7862s\\Downloads\\SamsungDeXSetupWin.exe",
        "C:\\Users\\7862s\\Downloads\\Rainmeter-4.5.17.exe",
        "C:\\Users\\7862s\\Downloads\\jdk-20_windows-x64_bin.msi",
        "C:\\Users\\7862s\\Downloads\\OpenJDK17U-jdk_x64_windows_hotspot_17.0.7_7.msi",
        "C:\\Users\\7862s\\Downloads\\tsetup-x64.4.8.3.exe",
        # "D:\\Clips\\20240308_131433.mp4",
        # "D:\\Clips\\20240308_131433.mp4",
        # "D:\\Clips\\20240308_132539.mp4",
        # "D:\\Clips\\20240308_132643.mp4",
        # "D:\\Clips\\20240308_132742.mp4",
        # "D:\\Clips\\20240308_132816.mp4",
        # "D:\\Clips\\20240308_132838.mp4",
        # "D:\\Clips\\20240308_132908.mp4",
        # "D:\\Clips\\20240308_133024.mp4",
        # "D:\\Clips\\20240308_133024.mp4",
        # "D:\\Clips\\20240308_133024.mp4",
        "D:\\Movies\\Dead pool 1.mkv",
        "D:\\Movies\\Fifty.Shades.of.Grey.2015.UNRATED.BRRip.XviD-ETRG.avi",
        "D:\\Movies\\K_G_F_Chapter_2.mkv",
        "D:\\Movies\\Predestination.2014.720p.BluRay.x264.700MB-[Mkvking.com].mkv",
        "D:\\Movies\\Transformers_Rise_of_the_Beasts_2023_1080p_WEBRip_x265_10bit_Telugu.mkv",
        "D:\\Movies\\Fifty.Shades.of.Grey.2015.UNRATED.BRRip.XviD-ETRG.avi",
        "D:\\Movies\\K_G_F_Chapter_2.mkv",
        "D:\\Movies\\Predestination.2014.720p.BluRay.x264.700MB-[Mkvking.com].mkv",
        "D:\\Movies\\Transformers_Rise_of_the_Beasts_2023_1080p_WEBRip_x265_10bit_Telugu.mkv",
        "D:\\Movies\\Dead pool 1.mkv",
        "D:\\Movies\\Fifty.Shades.of.Grey.2015.UNRATED.BRRip.XviD-ETRG.avi",
        "D:\\Movies\\K_G_F_Chapter_2.mkv",
        "D:\\Movies\\Predestination.2014.720p.BluRay.x264.700MB-[Mkvking.com].mkv",
        "D:\\Movies\\Transformers_Rise_of_the_Beasts_2023_1080p_WEBRip_x265_10bit_Telugu.mkv",
        "D:\\Movies\\Fifty.Shades.of.Grey.2015.UNRATED.BRRip.XviD-ETRG.avi",
        "D:\\Movies\\K_G_F_Chapter_2.mkv",
        "D:\\Movies\\Predestination.2014.720p.BluRay.x264.700MB-[Mkvking.com].mkv",
        "D:\\Movies\\Transformers_Rise_of_the_Beasts_2023_1080p_WEBRip_x265_10bit_Telugu.mkv",
    ]
    file_s = make_file_items(paths=file_s)

    gr = _FileGroup(files=file_s, level=GROUP_MIN)

    gr.group()
    print(gr)
    # _PeerFile(file_s)

    # for p in gr:
    #     print(f"({p[1] // 1024}MB): {", ".join(f"({x[0][-10:]},{x[1]})" for x in p[1:])}")
