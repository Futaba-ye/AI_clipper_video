# 兼容层：原有导入路径仍然可用
# 新代码请直接从对应模块导入

from app.utils.VTT_time import transform_vtt_time, parse_vtt_ts
from app.utils.VTT_writer import sanitize_filename, safe_open, write_vtt, write_formatted_vtt
from app.utils.VTT_parser import make_chunk_vtt, parse_vtt_to_subtitles, parse_vtt_to_raw_subtitles, scenes_to_vtt
