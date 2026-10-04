-- INU Tools: standalone COL material, original implementation.
plugin material INU_GTA_COLSurface name:"INU GTA COL Surface" classID:#(0x6a415521,0x37b06913) extends:Standard replaceUI:true version:1
(
parameters main rollout:colUI
(
surface type:#integer default:0 ui:ui_surface
flags type:#integer default:0 ui:ui_flags
brightness type:#integer default:0 ui:ui_brightness
dayLight type:#integer default:0 ui:ui_day
nightLight type:#integer default:0 ui:ui_night
previewColor type:#color default:(color 120 200 120) ui:ui_color
on previewColor set value do delegate.diffuse=value
)
rollout colUI "Collision Parameters"
(
dropdownlist ui_type "Surface type" items:#("0: DEFAULT", "1: TARMAC", "2: TARMAC_FUCKED", "3: TARMAC_REALLYFUCKED", "4: PAVEMENT", "5: PAVEMENT_FUCKED", "6: GRAVEL", "7: FUCKED_CONCRETE", "8: PAINTED_GROUND", "9: GRASS_SHORT_LUSH", "10: GRASS_MEDIUM_LUSH", "11: GRASS_LONG_LUSH", "12: GRASS_SHORT_DRY", "13: GRASS_MEDIUM_DRY", "14: GRASS_LONG_DRY", "15: GOLFGRASS_ROUGH", "16: GOLFGRASS_SMOOTH", "17: STEEP_SLIDYGRASS", "18: STEEP_CLIFF", "19: FLOWERBED", "20: MEADOW", "21: WASTEGROUND", "22: WOODLANDGROUND", "23: VEGETATION", "24: MUD_WET", "25: MUD_DRY", "26: DIRT", "27: DIRTTRACK", "28: SAND_DEEP", "29: SAND_MEDIUM", "30: SAND_COMPACT", "31: SAND_ARID", "32: SAND_MORE", "33: SAND_BEACH", "34: CONCRETE_BEACH", "35: ROCK_DRY", "36: ROCK_WET", "37: ROCK_CLIFF", "38: WATER_RIVERBED", "39: WATER_SHALLOW", "40: CORNFIELD", "41: HEDGE", "42: WOOD_CRATES", "43: WOOD_SOLID", "44: WOOD_THIN", "45: GLASS", "46: GLASS_WINDOWS_LARGE", "47: GLASS_WINDOWS_SMALL", "48: EMPTY1", "49: EMPTY2", "50: GARAGE_DOOR", "51: THICK_METAL_PLATE", "52: SCAFFOLD_POLE", "53: LAMP_POST", "54: METAL_GATE", "55: METAL_CHAIN_FENCE", "56: GIRDER", "57: FIRE_HYDRANT", "58: CONTAINER", "59: NEWS_VENDOR", "60: WHEELBASE", "61: CARDBOARDBOX", "62: PED", "63: CAR", "64: CAR_PANEL", "65: CAR_MOVINGCOMPONENT", "66: TRANSPARENT_CLOTH", "67: RUBBER", "68: PLASTIC", "69: TRANSPARENT_STONE", "70: WOOD_BENCH", "71: CARPET", "72: FLOORBOARD", "73: STAIRSWOOD", "74: P_SAND", "75: P_SAND_DENSE", "76: P_SAND_ARID", "77: P_SAND_COMPACT", "78: P_SAND_ROCKY", "79: P_SAND_BEACH", "80: P_GRASS_SHORT", "81: P_GRASS_MEADOW", "82: P_GRASS_DRY", "83: P_WOODLAND", "84: P_WOODDENSE", "85: P_ROADSIDE", "86: P_ROADSIDEDES", "87: P_FLOWERBED", "88: P_WASTEGROUND", "89: P_CONCRETE", "90: P_OFFICEDESK", "91: P_711SHELF1", "92: P_711SHELF2", "93: P_711SHELF3", "94: P_RESTURANTTABLE", "95: P_BARTABLE", "96: P_UNDERWATERLUSH", "97: P_UNDERWATERBARREN", "98: P_UNDERWATERCORAL", "99: P_UNDERWATERDEEP", "100: P_RIVERBED", "101: P_RUBBLE", "102: P_BEDROOMFLOOR", "103: P_KITCHENFLOOR", "104: P_LIVINGROOMFLOOR", "105: P_CORRIDORFLOOR", "106: P_711FLOOR", "107: P_ABORETUMFLOOR", "108: P_SKANKYFLOOR", "109: P_MOUNTAIN", "110: P_MARSH", "111: P_BUSHY", "112: P_BUSHYMIX", "113: P_BUSHYDRY", "114: P_BUSHYMID", "115: P_GRASSWEEFLOWERS", "116: P_GRASSDRYTALL", "117: P_GRASSLUSHTALL", "118: P_GRASSGREENMIX", "119: P_GRASSBROWNMIX", "120: P_GRASSLOW", "121: P_GRASSROCKY", "122: P_GRASSSMALLTREES", "123: P_DIRTROCKY", "124: P_DIRTWEEDS", "125: P_GRASSWEEDS", "126: P_RIVEREDGE", "127: P_POOLSIDE", "128: P_FORESTSTUMPS", "129: P_FORESTSTICKS", "130: P_FORESTLEAVES", "131: P_DESERTROCKS", "132: P_FORRESTDRY", "133: P_SPARSEFLOWERS", "134: P_BUILDINGSITE", "135: P_DOCKLANDS", "136: P_INDUSTRIAL", "137: P_INDUSTJETTY", "138: P_CONCRETELITTER", "139: P_ALLEYRUBISH", "140: P_JUNKYARDPILES", "141: P_JUNKYARDGRND", "142: P_DUMP", "143: P_CACTUSDENSE", "144: P_AIRPORTGND", "145: P_CORNFIELD", "146: P_YOURGRASS1", "147: P_YOURGRASS2", "148: P_YOURGRASS3", "149: P_GRASSMID1", "150: P_GRASSMID2", "151: P_GRASSDARK", "152: P_GRASSDARK2", "153: P_GRASSDIRTMIX", "154: P_RIVERBEDSTONE", "155: P_RIVERBEDSHALLOW", "156: P_RIVERBEDWEEDS", "157: P_SEAWEED", "158: DOOR", "159: PLASTICBARRIER", "160: PARKGRASS", "161: STAIRSSTONE", "162: STAIRSMETAL", "163: STAIRSCARPET", "164: FLOORMETAL", "165: FLOORCONCRETE", "166: BIN_BAG", "167: THIN_METAL_SHEET", "168: METAL_BARREL", "169: PLASTIC_CONE", "170: PLASTIC_DUMPSTER", "171: METAL_DUMPSTER", "172: WOOD_PICKET_FENCE", "173: WOOD_SLATTED_FENCE", "174: WOOD_RANCH_FENCE", "175: UNBREAKABLE_GLASS", "176: HAY_BALE", "177: GORE", "178: RAILTRACK", "179: UNKNOWN", "180: UNKNOWN", "181: UNKNOWN", "182: UNKNOWN", "183: UNKNOWN", "184: UNKNOWN", "185: UNKNOWN", "186: UNKNOWN", "187: UNKNOWN", "188: UNKNOWN", "189: UNKNOWN", "190: UNKNOWN", "191: UNKNOWN", "192: UNKNOWN", "193: UNKNOWN", "194: UNKNOWN", "195: UNKNOWN", "196: UNKNOWN", "197: UNKNOWN", "198: UNKNOWN", "199: UNKNOWN", "200: UNKNOWN", "201: UNKNOWN", "202: UNKNOWN", "203: UNKNOWN", "204: UNKNOWN", "205: UNKNOWN", "206: UNKNOWN", "207: UNKNOWN", "208: UNKNOWN", "209: UNKNOWN", "210: UNKNOWN", "211: UNKNOWN", "212: UNKNOWN", "213: UNKNOWN", "214: UNKNOWN", "215: UNKNOWN", "216: UNKNOWN", "217: UNKNOWN", "218: UNKNOWN", "219: UNKNOWN", "220: UNKNOWN", "221: UNKNOWN", "222: UNKNOWN", "223: UNKNOWN", "224: UNKNOWN", "225: UNKNOWN", "226: UNKNOWN", "227: UNKNOWN", "228: UNKNOWN", "229: UNKNOWN", "230: UNKNOWN", "231: UNKNOWN", "232: UNKNOWN", "233: UNKNOWN", "234: UNKNOWN", "235: UNKNOWN", "236: UNKNOWN", "237: UNKNOWN", "238: UNKNOWN", "239: UNKNOWN", "240: UNKNOWN", "241: UNKNOWN", "242: UNKNOWN", "243: UNKNOWN", "244: UNKNOWN", "245: UNKNOWN", "246: UNKNOWN", "247: UNKNOWN", "248: UNKNOWN", "249: UNKNOWN", "250: UNKNOWN", "251: UNKNOWN", "252: UNKNOWN", "253: UNKNOWN", "254: UNKNOWN", "255: UNKNOWN")
on ui_type selected index do surface=index-1
on colUI open do ui_type.selection=surface+1
on ui_surface changed value do ui_type.selection=value+1
spinner ui_surface "Surface ID" range:[0,255,0] type:#integer fieldwidth:55
spinner ui_flags "Flags byte" range:[0,255,0] type:#integer fieldwidth:55
spinner ui_brightness "Brightness / part byte" range:[0,255,0] type:#integer fieldwidth:55
spinner ui_day "Day light (COL1)" range:[0,15,0] type:#integer fieldwidth:55
spinner ui_night "Night light (COL1)" range:[0,15,0] type:#integer fieldwidth:55
colorpicker ui_color "Viewport color"
label info "Surface data is exported by INU COL IO."
)
on create do (delegate.diffuse=previewColor; delegate.specular=black; delegate.twoSided=true)
)

-- INU Tools: standalone COL material, original implementation.
plugin material INU_GTA_COLShadow name:"INU GTA COL Shadow" classID:#(0x6a415521,0x37b06914) extends:Standard replaceUI:true version:1
(
parameters main rollout:colUI
(
surface type:#integer default:0 ui:ui_surface
flags type:#integer default:0 ui:ui_flags
brightness type:#integer default:255 ui:ui_brightness
dayLight type:#integer default:0 ui:ui_day
nightLight type:#integer default:0 ui:ui_night
previewColor type:#color default:(color 60 60 60) ui:ui_color
on previewColor set value do delegate.diffuse=value
on brightness set value do delegate.opacity=value/255.0*100
)
rollout colUI "Shadow Parameters"
(
spinner ui_surface "Unknown 1 / material byte" range:[0,255,0] type:#integer fieldwidth:55
spinner ui_flags "Flags byte" range:[0,255,0] type:#integer fieldwidth:55
spinner ui_brightness "Brightness / part byte" range:[0,255,255] type:#integer fieldwidth:55
spinner ui_day "Day light (COL1)" range:[0,15,0] type:#integer fieldwidth:55
spinner ui_night "Night light (COL1)" range:[0,15,0] type:#integer fieldwidth:55
colorpicker ui_color "Viewport color"
label info "Surface data is exported by INU COL IO."
)
on create do (delegate.diffuse=previewColor; delegate.specular=black; delegate.twoSided=true)
)
