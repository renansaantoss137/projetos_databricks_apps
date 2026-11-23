import pandas as pd

excel_data = {
    'ABRACCIO': {'act': 25581, 'bgt': 0, 'var_bgt': 0, 'py': 29515, 'var_py': -13, 'act_pct': 35, 'bgt_pct': 0, 'py_pct': 27},
    'ALPI': {'act': 206482, 'bgt': 252555, 'var_bgt': -18, 'py': 103602, 'var_py': 99, 'act_pct': 66, 'bgt_pct': 65, 'py_pct': 57},
    'BLUE FOOD SERVICE': {'act': 687186, 'bgt': 1657115, 'var_bgt': -59, 'py': 384391, 'var_py': 79, 'act_pct': 67, 'bgt_pct': 63, 'py_pct': 56},
    'BOB´S': {'act': 373218, 'bgt': 845050, 'var_bgt': -56, 'py': 476365, 'var_py': -22, 'act_pct': 36, 'bgt_pct': 51, 'py_pct': 42},
    'BRF': {'act': 1158432, 'bgt': 1307006, 'var_bgt': -11, 'py': 855086, 'var_py': 35, 'act_pct': 52, 'bgt_pct': 47, 'py_pct': 41},
    'BURGER FOODS': {'act': 242358, 'bgt': 424856, 'var_bgt': -43, 'py': 133163, 'var_py': 82, 'act_pct': 63, 'bgt_pct': 66, 'py_pct': 56},
    'BURGER KING': {'act': 6002041, 'bgt': 6445901, 'var_bgt': -7, 'py': 5548596, 'var_py': 8, 'act_pct': 55, 'bgt_pct': 43, 'py_pct': 44},
    'BUY FOODS': {'act': 671780, 'bgt': 701446, 'var_bgt': -4, 'py': 278723, 'var_py': 141, 'act_pct': 70, 'bgt_pct': 67, 'py_pct': 57},
    'CAMARADA CAMARÃO': {'act': 11859, 'bgt': 26618, 'var_bgt': -55, 'py': 0, 'var_py': 0, 'act_pct': 71, 'bgt_pct': 71, 'py_pct': 0},
    'CASTRO': {'act': 64015, 'bgt': 101620, 'var_bgt': -37, 'py': 24806, 'var_py': 158, 'act_pct': 62, 'bgt_pct': 62, 'py_pct': 54},
    'CECOTI': {'act': 79409, 'bgt': 157152, 'var_bgt': -49, 'py': 63324, 'var_py': 25, 'act_pct': 84, 'bgt_pct': 68, 'py_pct': 67},
    'CHEF MINEIRO': {'act': 40834, 'bgt': 37723, 'var_bgt': 8, 'py': 0, 'var_py': 0, 'act_pct': 60, 'bgt_pct': 61, 'py_pct': 0},
    'CLIENTES E FORNECEDORES': {'act': 81608, 'bgt': 0, 'var_bgt': 0, 'py': 150973, 'var_py': -46, 'act_pct': 100, 'bgt_pct': 0, 'py_pct': 100},
    'COMERCIAL AC': {'act': 118103, 'bgt': 144934, 'var_bgt': -19, 'py': 135807, 'var_py': -13, 'act_pct': 63, 'bgt_pct': 64, 'py_pct': 54},
    'DALAC': {'act': 47698, 'bgt': 66450, 'var_bgt': -28, 'py': 13535, 'var_py': 252, 'act_pct': 63, 'bgt_pct': 60, 'py_pct': 47},
    'DEMARCHI BELEM': {'act': 30116, 'bgt': 34907, 'var_bgt': -14, 'py': 11720, 'var_py': 157, 'act_pct': 64, 'bgt_pct': 62, 'py_pct': 46},
    'DEMARCHI BRASILIA': {'act': 175461, 'bgt': 163983, 'var_bgt': 7, 'py': 48428, 'var_py': 262, 'act_pct': 62, 'bgt_pct': 63, 'py_pct': 56},
    'DEMARCHI CURITIBA': {'act': 205372, 'bgt': 270238, 'var_bgt': -24, 'py': 85449, 'var_py': 140, 'act_pct': 62, 'bgt_pct': 63, 'py_pct': 53},
    'DEMARCHI MANAUS': {'act': 27185, 'bgt': 0, 'var_bgt': 0, 'py': 0, 'var_py': 0, 'act_pct': 68, 'bgt_pct': 0, 'py_pct': 0},
    'DEMARCHI MARINGÁ': {'act': 206166, 'bgt': 219771, 'var_bgt': -6, 'py': 52850, 'var_py': 290, 'act_pct': 60, 'bgt_pct': 63, 'py_pct': 54},
    'DEMARCHI MINAS': {'act': 311005, 'bgt': 333935, 'var_bgt': -7, 'py': 128361, 'var_py': 142, 'act_pct': 67, 'bgt_pct': 63, 'py_pct': 55},
    'DEMARCHI RECIFE': {'act': 40342, 'bgt': 31490, 'var_bgt': 28, 'py': 24841, 'var_py': 62, 'act_pct': 60, 'bgt_pct': 61, 'py_pct': 46},
    'DUCAL': {'act': 31388, 'bgt': 42580, 'var_bgt': -26, 'py': 38504, 'var_py': -18, 'act_pct': 59, 'bgt_pct': 62, 'py_pct': 49},
    'FAMILY GO': {'act': 167418, 'bgt': 260336, 'var_bgt': -36, 'py': 90093, 'var_py': 86, 'act_pct': 59, 'bgt_pct': 62, 'py_pct': 54},
    'FOCATTO': {'act': 507765, 'bgt': 572059, 'var_bgt': -11, 'py': 229282, 'var_py': 121, 'act_pct': 63, 'bgt_pct': 63, 'py_pct': 53},
    'FRANGO ASSADO': {'act': 11423, 'bgt': 12527, 'var_bgt': -9, 'py': 8158, 'var_py': 40, 'act_pct': 67, 'bgt_pct': 70, 'py_pct': 57},
    'FRIGODARIO COMERCIAL': {'act': 245247, 'bgt': 0, 'var_bgt': 0, 'py': 0, 'var_py': 0, 'act_pct': 65, 'bgt_pct': 0, 'py_pct': 0},
    'GARDEN': {'act': 341149, 'bgt': 456937, 'var_bgt': -25, 'py': 175894, 'var_py': 94, 'act_pct': 63, 'bgt_pct': 63, 'py_pct': 55},
    'GLOBAL MALLE': {'act': 177986, 'bgt': 151430, 'var_bgt': 18, 'py': 171098, 'var_py': 4, 'act_pct': 64, 'bgt_pct': 65, 'py_pct': 56},
    'GRILETTO': {'act': 10554, 'bgt': 0, 'var_bgt': 0, 'py': 0, 'var_py': 0, 'act_pct': 65, 'bgt_pct': 0, 'py_pct': 0},
    'HOLCASHER': {'act': 0, 'bgt': 24743, 'var_bgt': -100, 'py': 0, 'var_py': 0, 'act_pct': 0, 'bgt_pct': 67, 'py_pct': 0},
    'ICE LOG': {'act': 293649, 'bgt': 151813, 'var_bgt': 93, 'py': 220552, 'var_py': 33, 'act_pct': 69, 'bgt_pct': 64, 'py_pct': 54},
    'ITAVALE': {'act': 122134, 'bgt': 88245, 'var_bgt': 38, 'py': 28187, 'var_py': 333, 'act_pct': 82, 'bgt_pct': 64, 'py_pct': 63},
    'JOHNNY ROCKETS': {'act': 0, 'bgt': 2381, 'var_bgt': -100, 'py': 0, 'var_py': 0, 'act_pct': 0, 'bgt_pct': 55, 'py_pct': 0},
    'K2': {'act': 289476, 'bgt': 222705, 'var_bgt': 30, 'py': 236992, 'var_py': 22, 'act_pct': 62, 'bgt_pct': 64, 'py_pct': 53},
    'KAV FOOD DIST': {'act': 112687, 'bgt': 36480, 'var_bgt': 209, 'py': 97223, 'var_py': 16, 'act_pct': 59, 'bgt_pct': 61, 'py_pct': 53},
    'KFC': {'act': 959576, 'bgt': 797909, 'var_bgt': 20, 'py': 697692, 'var_py': 38, 'act_pct': 42, 'bgt_pct': 48, 'py_pct': 46},
    'LOGICA JDF': {'act': 79931, 'bgt': 0, 'var_bgt': 0, 'py': 0, 'var_py': 0, 'act_pct': 81, 'bgt_pct': 0, 'py_pct': 0},
    'MC DONALDS': {'act': 11806191, 'bgt': 10150393, 'var_bgt': 16, 'py': 11128987, 'var_py': 6, 'act_pct': 50, 'bgt_pct': 45, 'py_pct': 46},
    'MEZZANI': {'act': 215607, 'bgt': 455810, 'var_bgt': -53, 'py': 247098, 'var_py': -13, 'act_pct': 56, 'bgt_pct': 53, 'py_pct': 57},
    'MONTE SION': {'act': 404280, 'bgt': 242209, 'var_bgt': 67, 'py': 75697, 'var_py': 434, 'act_pct': 66, 'bgt_pct': 57, 'py_pct': 49},
    'MULTIFRIOS': {'act': 55740, 'bgt': 113669, 'var_bgt': -51, 'py': 57519, 'var_py': -3, 'act_pct': 61, 'bgt_pct': 61, 'py_pct': 50},
    'NETFEIRA': {'act': 193156, 'bgt': 175543, 'var_bgt': 10, 'py': 52978, 'var_py': 265, 'act_pct': 65, 'bgt_pct': 64, 'py_pct': 59},
    'OUTBACK': {'act': 1534549, 'bgt': 1783716, 'var_bgt': -14, 'py': 1596404, 'var_py': -4, 'act_pct': 72, 'bgt_pct': 65, 'py_pct': 64},
    'PANTOJA': {'act': 912607, 'bgt': 1322409, 'var_bgt': -31, 'py': 551737, 'var_py': 65, 'act_pct': 44, 'bgt_pct': 59, 'py_pct': 30},
    'PARAGUAI': {'act': 0, 'bgt': 0, 'var_bgt': 0, 'py': 0, 'var_py': 0, 'act_pct': 0, 'bgt_pct': 0, 'py_pct': 0},
    'PAZOTTI': {'act': 61823, 'bgt': 124105, 'var_bgt': -50, 'py': 92661, 'var_py': -33, 'act_pct': 69, 'bgt_pct': 66, 'py_pct': 57},
    'POLINA': {'act': 92587, 'bgt': 149582, 'var_bgt': -38, 'py': 94300, 'var_py': -2, 'act_pct': 60, 'bgt_pct': 60, 'py_pct': 51},
    'POPEYES': {'act': 285788, 'bgt': 365193, 'var_bgt': -22, 'py': 253689, 'var_py': 13, 'act_pct': 49, 'bgt_pct': 43, 'py_pct': 39},
    'PROSPECT I': {'act': 0, 'bgt': 347697, 'var_bgt': -100, 'py': 0, 'var_py': 0, 'act_pct': 0, 'bgt_pct': 57, 'py_pct': 0},
    'PROSPECT II': {'act': 0, 'bgt': 347697, 'var_bgt': -100, 'py': 0, 'var_py': 0, 'act_pct': 0, 'bgt_pct': 57, 'py_pct': 0},
    'RIOFRUT': {'act': 46884, 'bgt': 160760, 'var_bgt': -71, 'py': 154466, 'var_py': -70, 'act_pct': 65, 'bgt_pct': 66, 'py_pct': 59},
    'ROCK RIBS': {'act': 0, 'bgt': 13013, 'var_bgt': -100, 'py': 0, 'var_py': 0, 'act_pct': 0, 'bgt_pct': 69, 'py_pct': 0},
    'SAM´SCLUB': {'act': 75243, 'bgt': 151256, 'var_bgt': -50, 'py': 68300, 'var_py': 10, 'act_pct': 63, 'bgt_pct': 64, 'py_pct': 52.8},
    'SAPORE': {'act': 0, 'bgt': 52480, 'var_bgt': -100, 'py': 0, 'var_py': 0, 'act_pct': 0, 'bgt_pct': 60.6, 'py_pct': 0},
    'SEARA': {'act': 560162, 'bgt': 759473, 'var_bgt': -26, 'py': 487729, 'var_py': 15, 'act_pct': 38, 'bgt_pct': 40, 'py_pct': 34},
    'SPEERS DISTRIBUIDORA': {'act': 253559, 'bgt': 376284, 'var_bgt': -32, 'py': 143895, 'var_py': 76, 'act_pct': 67, 'bgt_pct': 66, 'py_pct': 56},
    'SUBWAY': {'act': 1926384, 'bgt': 2811481, 'var_bgt': -31, 'py': 1012082, 'var_py': 90, 'act_pct': 29, 'bgt_pct': 47, 'py_pct': 20},
    'URUGUAI': {'act': -5245, 'bgt': -37648, 'var_bgt': -86, 'py': -3372, 'var_py': 56, 'act_pct': -6, 'bgt_pct': -93, 'py_pct': -3},
    'VIVA BROKER': {'act': 0, 'bgt': 90640, 'var_bgt': -100, 'py': 0, 'var_py': 0, 'act_pct': 0, 'bgt_pct': 63, 'py_pct': 0}
}

app_data = {
    'ABRACCIO': {'act': 25581, 'bgt': 0, 'var_bgt': 0.0, 'py': 16884, 'var_py': 51.5, 'act_pct': 34.8, 'bgt_pct': 0.0, 'py_pct': 28.7},
    'ALPI': {'act': 206482, 'bgt': 252555, 'var_bgt': -18.2, 'py': 103602, 'var_py': 99.3, 'act_pct': 66.2, 'bgt_pct': 64.6, 'py_pct': 56.5},
    'BLUE FOOD SERVICE': {'act': 687186, 'bgt': 1657115, 'var_bgt': -58.5, 'py': 283393, 'var_py': 142.5, 'act_pct': 66.8, 'bgt_pct': 62.7, 'py_pct': 55.0},
    'BOB´S': {'act': 305405, 'bgt': 743731, 'var_bgt': -58.9, 'py': 354747, 'var_py': -13.9, 'act_pct': 34.4, 'bgt_pct': 50.5, 'py_pct': 41.5},
    'BRF': {'act': 859946, 'bgt': 1307006, 'var_bgt': -34.2, 'py': 642949, 'var_py': 33.8, 'act_pct': 55.8, 'bgt_pct': 46.9, 'py_pct': 48.7},
    'BURGER FOODS': {'act': 242358, 'bgt': 424856, 'var_bgt': -43.0, 'py': 133163, 'var_py': 82.0, 'act_pct': 63.5, 'bgt_pct': 65.6, 'py_pct': 56.3},
    'BURGER KING': {'act': 3275684, 'bgt': 903210, 'var_bgt': 262.7, 'py': 2489350, 'var_py': 31.6, 'act_pct': 50.2, 'bgt_pct': 42.9, 'py_pct': 43.1},
    'BUY FOODS': {'act': 671780, 'bgt': 701446, 'var_bgt': -4.2, 'py': 224038, 'var_py': 199.9, 'act_pct': 70.3, 'bgt_pct': 67.0, 'py_pct': 56.4},
    'CAMARADA CAMARÃO': {'act': 11859, 'bgt': 26618, 'var_bgt': -55.4, 'py': 0, 'var_py': 0.0, 'act_pct': 71.1, 'bgt_pct': 71.3, 'py_pct': 0.0},
    'CASTRO': {'act': 64015, 'bgt': 101620, 'var_bgt': -37.0, 'py': 24806, 'var_py': 158.1, 'act_pct': 61.9, 'bgt_pct': 61.9, 'py_pct': 53.7},
    'CECOTI': {'act': 79409, 'bgt': 157152, 'var_bgt': -49.5, 'py': 63324, 'var_py': 25.4, 'act_pct': 84.0, 'bgt_pct': 67.7, 'py_pct': 67.5},
    'CHEF MINEIRO': {'act': 40834, 'bgt': 37723, 'var_bgt': 8.2, 'py': 0, 'var_py': 0.0, 'act_pct': 60.1, 'bgt_pct': 61.0, 'py_pct': 0.0},
    'COMERCIAL AC': {'act': 118103, 'bgt': 144934, 'var_bgt': -18.5, 'py': 135807, 'var_py': -13.0, 'act_pct': 63.3, 'bgt_pct': 64.4, 'py_pct': 54.3},
    'DALAC': {'act': 47698, 'bgt': 66450, 'var_bgt': -28.2, 'py': 13535, 'var_py': 252.4, 'act_pct': 62.8, 'bgt_pct': 60.0, 'py_pct': 47.5},
    'DEMARCHI BELEM': {'act': 30116, 'bgt': 34907, 'var_bgt': -13.7, 'py': 11720, 'var_py': 157.0, 'act_pct': 63.5, 'bgt_pct': 62.1, 'py_pct': 46.0},
    'DEMARCHI BRASILIA': {'act': 175461, 'bgt': 163983, 'var_bgt': 7.0, 'py': 48428, 'var_py': 262.3, 'act_pct': 61.7, 'bgt_pct': 63.0, 'py_pct': 56.2},
    'DEMARCHI CURITIBA': {'act': 205372, 'bgt': 270238, 'var_bgt': -24.0, 'py': 85449, 'var_py': 140.3, 'act_pct': 62.2, 'bgt_pct': 62.6, 'py_pct': 53.5},
    'DEMARCHI MANAUS': {'act': 27185, 'bgt': 0, 'var_bgt': 0.0, 'py': 0, 'var_py': 0.0, 'act_pct': 67.9, 'bgt_pct': 0.0, 'py_pct': 0.0},
    'DEMARCHI MARINGÁ': {'act': 50997, 'bgt': 219771, 'var_bgt': -76.8, 'py': 52850, 'var_py': -3.5, 'act_pct': 53.2, 'bgt_pct': 63.1, 'py_pct': 54.1},
    'DEMARCHI MINAS': {'act': 311005, 'bgt': 333935, 'var_bgt': -6.9, 'py': 128361, 'var_py': 142.3, 'act_pct': 66.5, 'bgt_pct': 62.7, 'py_pct': 55.0},
    'DEMARCHI RECIFE': {'act': 40342, 'bgt': 31490, 'var_bgt': 28.1, 'py': 24841, 'var_py': 62.4, 'act_pct': 59.8, 'bgt_pct': 60.7, 'py_pct': 45.8},
    'DUCAL': {'act': 31388, 'bgt': 42580, 'var_bgt': -26.3, 'py': 38504, 'var_py': -18.5, 'act_pct': 59.3, 'bgt_pct': 62.3, 'py_pct': 48.7},
    'FAMILY GO': {'act': 77353, 'bgt': 260336, 'var_bgt': -70.3, 'py': 90093, 'var_py': -14.1, 'act_pct': 54.1, 'bgt_pct': 61.7, 'py_pct': 53.9},
    'FOCATTO': {'act': 507765, 'bgt': 572059, 'var_bgt': -11.2, 'py': 191068, 'var_py': 165.8, 'act_pct': 62.8, 'bgt_pct': 63.2, 'py_pct': 53.1},
    'FRANGO ASSADO': {'act': 11423, 'bgt': 12527, 'var_bgt': -8.8, 'py': 8158, 'var_py': 40.0, 'act_pct': 67.2, 'bgt_pct': 70.2, 'py_pct': 57.2},
    'FRIGODARIO COMERCIAL': {'act': 245247, 'bgt': 0, 'var_bgt': 0.0, 'py': 0, 'var_py': 0.0, 'act_pct': 64.7, 'bgt_pct': 0.0, 'py_pct': 0.0},
    'GARDEN': {'act': 341149, 'bgt': 456937, 'var_bgt': -25.3, 'py': 175894, 'var_py': 94.0, 'act_pct': 63.2, 'bgt_pct': 63.3, 'py_pct': 55.7},
    'GLOBAL MALLE': {'act': 177986, 'bgt': 151430, 'var_bgt': 17.5, 'py': 171098, 'var_py': 4.0, 'act_pct': 64.2, 'bgt_pct': 65.3, 'py_pct': 56.0},
    'GRILETTO': {'act': 10554, 'bgt': 0, 'var_bgt': 0.0, 'py': 0, 'var_py': 0.0, 'act_pct': 65.4, 'bgt_pct': 0.0, 'py_pct': 0.0},
    'HOLCASHER': {'act': 0, 'bgt': 24743, 'var_bgt': -100.0, 'py': 0, 'var_py': 0.0, 'act_pct': 0.0, 'bgt_pct': 66.5, 'py_pct': 0.0},
    'ICE LOG': {'act': 293649, 'bgt': 151813, 'var_bgt': 93.4, 'py': 144548, 'var_py': 103.2, 'act_pct': 69.4, 'bgt_pct': 63.9, 'py_pct': 54.6},
    'ITAVALE': {'act': 122134, 'bgt': 88245, 'var_bgt': 38.4, 'py': 28187, 'var_py': 333.3, 'act_pct': 82.0, 'bgt_pct': 63.7, 'py_pct': 62.8},
    'JOHNNY ROCKETS': {'act': 0, 'bgt': 2381, 'var_bgt': -100.0, 'py': 0, 'var_py': 0.0, 'act_pct': 0.0, 'bgt_pct': 55.0, 'py_pct': 0.0},
    'K2': {'act': 289476, 'bgt': 222705, 'var_bgt': 30.0, 'py': 201537, 'var_py': 43.6, 'act_pct': 62.1, 'bgt_pct': 64.1, 'py_pct': 53.0},
    'KAV FOOD DIST': {'act': 112687, 'bgt': 36480, 'var_bgt': 208.9, 'py': 97223, 'var_py': 15.9, 'act_pct': 59.3, 'bgt_pct': 60.9, 'py_pct': 53.3},
    'KFC': {'act': 827058, 'bgt': 797909, 'var_bgt': 3.7, 'py': 248072, 'var_py': 233.4, 'act_pct': 40.9, 'bgt_pct': 47.7, 'py_pct': 47.3},
    'LOGICA JDF': {'act': 79931, 'bgt': 0, 'var_bgt': 0.0, 'py': 0, 'var_py': 0.0, 'act_pct': 80.9, 'bgt_pct': 0.0, 'py_pct': 0.0},
    'MC DONALDS': {'act': 6595574, 'bgt': 6095043, 'var_bgt': 8.2, 'py': 5352005, 'var_py': 23.2, 'act_pct': 44.5, 'bgt_pct': 41.7, 'py_pct': 43.1},
    'MEZZANI': {'act': 215607, 'bgt': 455810, 'var_bgt': -52.7, 'py': 170398, 'var_py': 26.5, 'act_pct': 56.2, 'bgt_pct': 53.5, 'py_pct': 57.3},
    'MONTE SION': {'act': 404280, 'bgt': 242209, 'var_bgt': 66.9, 'py': 75697, 'var_py': 434.1, 'act_pct': 66.0, 'bgt_pct': 57.1, 'py_pct': 49.1},
    'MULTIFRIOS': {'act': 55740, 'bgt': 113669, 'var_bgt': -51.0, 'py': 23557, 'var_py': 136.6, 'act_pct': 61.1, 'bgt_pct': 61.0, 'py_pct': 51.1},
    'NETFEIRA': {'act': 193156, 'bgt': 175543, 'var_bgt': 10.0, 'py': 52978, 'var_py': 264.6, 'act_pct': 65.4, 'bgt_pct': 63.7, 'py_pct': 59.0},
    'OUTBACK': {'act': 673484, 'bgt': 886540, 'var_bgt': -24.0, 'py': 1386390, 'var_py': -51.4, 'act_pct': 59.3, 'bgt_pct': 65.1, 'py_pct': 64.7},
    'PANTOJA': {'act': 912607, 'bgt': 1322409, 'var_bgt': -31.0, 'py': 551737, 'var_py': 65.4, 'act_pct': 43.7, 'bgt_pct': 58.8, 'py_pct': 29.7},
    'PARAGUAI': {'act': 0, 'bgt': 0, 'var_bgt': 0.0, 'py': 0, 'var_py': 0.0, 'act_pct': 0.0, 'bgt_pct': 0.0, 'py_pct': 0.0},
    'PAZOTTI': {'act': 61823, 'bgt': 124105, 'var_bgt': -50.2, 'py': 92661, 'var_py': -33.3, 'act_pct': 68.5, 'bgt_pct': 66.0, 'py_pct': 57.3},
    'POLINA': {'act': 92587, 'bgt': 149582, 'var_bgt': -38.1, 'py': 68764, 'var_py': 34.6, 'act_pct': 59.8, 'bgt_pct': 60.3, 'py_pct': 50.3},
    'POPEYES': {'act': 285788, 'bgt': 138984, 'var_bgt': 105.6, 'py': 222584, 'var_py': 28.4, 'act_pct': 48.8, 'bgt_pct': 41.1, 'py_pct': 40.5},
    'PROSPECT I': {'act': 0, 'bgt': 347697, 'var_bgt': -100.0, 'py': 0, 'var_py': 0.0, 'act_pct': 0.0, 'bgt_pct': 57.1, 'py_pct': 0.0},
    'PROSPECT II': {'act': 0, 'bgt': 347697, 'var_bgt': -100.0, 'py': 0, 'var_py': 0.0, 'act_pct': 0.0, 'bgt_pct': 57.1, 'py_pct': 0.0},
    'RIOFRUT': {'act': 46884, 'bgt': 160760, 'var_bgt': -70.8, 'py': 154466, 'var_py': -69.6, 'act_pct': 64.7, 'bgt_pct': 66.5, 'py_pct': 58.7},
    'ROCK RIBS': {'act': 0, 'bgt': 13013, 'var_bgt': -100.0, 'py': 0, 'var_py': 0.0, 'act_pct': 0.0, 'bgt_pct': 69.3, 'py_pct': 0.0},
    'SAM´SCLUB': {'act': 75243, 'bgt': 151256, 'var_bgt': -50.3, 'py': 68300, 'var_py': 10.2, 'act_pct': 63.3, 'bgt_pct': 64.2, 'py_pct': 52.8},
    'SAPORE': {'act': 0, 'bgt': 52480, 'var_bgt': -100.0, 'py': 0, 'var_py': 0.0, 'act_pct': 0.0, 'bgt_pct': 60.6, 'py_pct': 0.0},
    'SEARA': {'act': 111690, 'bgt': 759473, 'var_bgt': -85.3, 'py': 226036, 'var_py': -50.6, 'act_pct': 44.7, 'bgt_pct': 40.4, 'py_pct': 47.0},
    'SPEERS DISTRIBUIDORA': {'act': 253559, 'bgt': 376284, 'var_bgt': -32.6, 'py': 143895, 'var_py': 76.2, 'act_pct': 66.7, 'bgt_pct': 66.2, 'py_pct': 56.1},
    'SUBWAY': {'act': 1926384, 'bgt': 448925, 'var_bgt': 329.1, 'py': 876798, 'var_py': 119.7, 'act_pct': 28.6, 'bgt_pct': 47.5, 'py_pct': 20.6},
    'URUGUAI': {'act': -5245, 'bgt': -37648, 'var_bgt': -86.1, 'py': -3372, 'var_py': 55.5, 'act_pct': -5.6, 'bgt_pct': -92.7, 'py_pct': -2.9},
    'VIVA BROKER': {'act': 0, 'bgt': 90640, 'var_bgt': -100.0, 'py': 0, 'var_py': 0.0, 'act_pct': 0.0, 'bgt_pct': 63.1, 'py_pct': 0.0}
}

diffs = []
matches = []

for cli, e_val in excel_data.items():
    if cli not in app_data:
        diffs.append((cli, 'EXCLUIDO_DO_APP', e_val, None))
        continue
    a_val = app_data[cli]
    act_diff = abs(e_val['act'] - a_val['act']) > 2
    bgt_diff = abs(e_val['bgt'] - a_val['bgt']) > 2
    py_diff = abs(e_val['py'] - a_val['py']) > 2
    
    if act_diff or bgt_diff or py_diff:
        diffs.append((cli, 'DIVERGENCIA', e_val, a_val))
    else:
        matches.append((cli, e_val, a_val))

print(f"Total clientes no Excel: {len(excel_data)}")
print(f"Total clientes 100% compativeis (ACT, BGT e PY): {len(matches)}")
print(f"Total clientes com divergencia: {len(diffs)}")

print("\n=== CLIENTES IDENTICOS ===")
for cli, e_val, a_val in matches:
    print(f"[OK] {cli:25s} | ACT={e_val['act']:>10,d} | BGT={e_val['bgt']:>10,d} | PY={e_val['py']:>10,d}")

print("\n=== CLIENTES COM DIVERGENCIA ===")
for cli, tipo, e_val, a_val in diffs:
    if a_val is None:
        print(f"[REMOVIDO NO APP] {cli:25s} | Excel ACT={e_val['act']:,d}, PY={e_val['py']:,d}")
    else:
        d_str = []
        if abs(e_val['act'] - a_val['act']) > 2:
            d_str.append(f"ACT: Exc={e_val['act']:>10,d} vs App={a_val['act']:>10,d} (dif: {a_val['act']-e_val['act']:>+10,d})")
        if abs(e_val['bgt'] - a_val['bgt']) > 2:
            d_str.append(f"BGT: Exc={e_val['bgt']:>10,d} vs App={a_val['bgt']:>10,d} (dif: {a_val['bgt']-e_val['bgt']:>+10,d})")
        if abs(e_val['py'] - a_val['py']) > 2:
            d_str.append(f"PY: Exc={e_val['py']:>10,d} vs App={a_val['py']:>10,d} (dif: {a_val['py']-e_val['py']:>+10,d})")
        print(f"[DIVERGENTE] {cli:25s} | " + " | ".join(d_str))
