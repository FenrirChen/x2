/* Host-side contract test. Uses opaque managed strings, never C string casts. */
#include "x2save_bridge.c"

static int login, input_account, input_password, account_string, password_string;
static int url_string, open_string, class_string, domain, assembly, image;
static int input_class, game_class, ajc_class, object_class, login_class;
static int field_account, field_password, field_url, method_text, method_ctor;
static int method_generic, method_static, void_type, generic_type, ajc_object;
static int invoked, failed, omit_symbol;
static struct {struct Il2CppArrayHead head; void* values[3];} array;

/* --- login title voice fixtures ----------------------------------------- */
static int account_class, dubbing_mgr_class, game_api_class;
static int wrapper_class, list_class, row_class;
static int dubbing_wrapper, dubbing_list, dubbing_row[3];
static int board_hero = 1014, dubbing_count = 3, played_dubbing_id;
static int field_items, field_rows, field_size, field_hero, field_name, field_id;
static struct {void* entry;} method_cur_hero, method_all_dubbing, method_play_voice;
static struct {struct Il2CppArrayHead head; void* values[3];} dubbing_rows;
static struct {int hero; int name; int id;} dubbing_table[3] = {
    {1014, 1350001, 1000},      /* another TianShu line: skipped on name */
    {1014, 1350035, 1351432},   /* TianShu's 标题 row, as audited in Dubbing.json */
    {1010, 1350035, 1351036},   /* ChuJiu's 标题 row: skipped on hero */
};

static void* mock_domain_get(void) {return &domain;}
static void* mock_thread_attach(void* p) {return p;}
static void* mock_get_corlib(void) {return &image;}
static void* mock_domain_assemblies(void* p, ulong_a* count) {
    static void* list[1]; list[0]=&assembly; *count=1; return list;
}
static void* mock_assembly_image(void* p) {return &image;}
static const char* mock_image_name(void* p) {return "Assembly-CSharp.dll";}
static void* mock_class_from_name(void* p, const char* ns, const char* n) {
    if(name_is(n,"GameConst")) return &game_class;
    if(name_is(n,"AndroidJavaClass")) return &ajc_class;
    if(name_is(n,"Object")) return &object_class;
    if(name_is(n,"AccountInfoModule")) return &account_class;
    if(name_is(n,"DubbingManager")) return &dubbing_mgr_class;
    if(name_is(n,"GameAPI")) return &game_api_class;
    return 0;
}
static void* mock_object_class(void* p) {
    if(p==&dubbing_wrapper) return &wrapper_class;
    if(p==&dubbing_list) return &list_class;
    for(int i=0;i<3;++i) if(p==&dubbing_row[i]) return &row_class;
    return p==&login ? &login_class : &input_class;
}
static void* mock_class_parent(void* p) {return 0;}
static void* mock_field_from_name(void* p, const char* n) {
    if(name_is(n,"mTxtAccount"))return &field_account;
    if(name_is(n,"mTxtPassword"))return &field_password;
    if(name_is(n,"Login_Url"))return &field_url;
    if(name_is(n,"Items"))return &field_items;
    if(name_is(n,"_items"))return &field_rows;
    if(name_is(n,"_size"))return &field_size;
    if(name_is(n,"HeroId"))return &field_hero;
    if(name_is(n,"DubbingName"))return &field_name;
    if(name_is(n,"DubbingId"))return &field_id;
    return 0;
}
static void mock_field_get_value(void* p, void* f, void* out) {
    if(f==&field_items){*(void**)out=&dubbing_list;return;}
    if(f==&field_rows){*(void**)out=&dubbing_rows;return;}
    if(f==&field_size){*(int*)out=dubbing_count;return;}
    if(f==&field_hero||f==&field_name||f==&field_id){
        for(int i=0;i<dubbing_count;++i) if(p==&dubbing_row[i]){
            *(int*)out = f==&field_hero ? dubbing_table[i].hero
                       : f==&field_name ? dubbing_table[i].name
                       : dubbing_table[i].id;
            return;
        }
        failed=1;return;
    }
    *(void**)out=f==&field_account ? &input_account : &input_password;
}
static void mock_field_static_get_value(void* f, void* out) {*(void**)out=&url_string;}
static void* mock_method_from_name(void* p, const char* n, int arity) {
    if(name_is(n,"get_CurHero"))return &method_cur_hero;
    if(name_is(n,"GetAllItem"))return &method_all_dubbing;
    if(name_is(n,"PlayVoice"))return &method_play_voice;
    return name_is(n,"get_text") ? &method_text : &method_ctor;
}
static void* mock_class_methods(void* p, void** it) {
    if(!*it){*it=&method_generic;return &method_generic;}
    if(*it==&method_generic){*it=&method_static;return &method_static;}
    return 0;
}
static const char* mock_method_name(void* p) {return "CallStatic";}
static int mock_method_param_count(void* p) {return 2;}
static void* mock_method_return_type(void* p) {
    return p==&method_generic ? &generic_type : &void_type;
}
static void* mock_object_new(void* p) {return &ajc_object;}
static void* mock_string_new(const char* p) {
    if(name_is(p,"open"))return &open_string;
    if(name_is(p,"com.siva.project.x2.SaveManagerBridge"))return &class_string;
    failed=1;return 0;
}
static void* mock_array_new(void* p, ulong_a n) {
    if(p!=&object_class || n!=3)failed=1;
    array.head.max_length=n;return &array;
}
static void* mock_runtime_invoke(void* m, void* p, void** args, void** exc) {
    *exc=0;
    if(m==&method_text)return p==&input_account ? &account_string : &password_string;
    if(m==&method_ctor){if(args[0]!=&class_string)failed=1;return 0;}
    if(m!=&method_static || args[0]!=&open_string || args[1]!=&array)failed=1;
    if(array.values[0]!=&account_string || array.values[1]!=&password_string
       || array.values[2]!=&url_string)failed=1;
    invoked++;return 0;
}
/* The trampoline ABI: methodPointer is MethodInfo's first member, so the bridge
 * reads it straight out of these handles and calls it with a null receiver. */
static int mock_get_cur_hero(void* self, void* method) {(void)self;(void)method;return board_hero;}
static void* mock_all_dubbing(void* self, void* method) {(void)self;(void)method;return &dubbing_wrapper;}
static void mock_play_voice(void* self, int dubbing_id, void* method) {
    (void)self;(void)method;played_dubbing_id=dubbing_id;
}
void* dlopen(const char* p,int flags) {return name_is(p,"libil2cpp.so") ? &image : 0;}
#define MAP(symbol, fn) if(name_is(p,symbol))return (void*)mock_##fn
void* dlsym(void* h,const char* p) {
    if(h!=&image) {failed=1;return 0;}
    if(omit_symbol && name_is(p,"il2cpp_class_get_field_from_name"))return 0;
    MAP("il2cpp_domain_get",domain_get); MAP("il2cpp_thread_attach",thread_attach);
    MAP("il2cpp_class_from_name",class_from_name); MAP("il2cpp_get_corlib",get_corlib);
    MAP("il2cpp_domain_get_assemblies",domain_assemblies);
    MAP("il2cpp_assembly_get_image",assembly_image); MAP("il2cpp_image_get_name",image_name);
    MAP("il2cpp_class_get_field_from_name",field_from_name);
    MAP("il2cpp_field_get_value",field_get_value);
    MAP("il2cpp_field_static_get_value",field_static_get_value);
    MAP("il2cpp_class_get_method_from_name",method_from_name);
    MAP("il2cpp_class_get_parent",class_parent); MAP("il2cpp_object_get_class",object_class);
    MAP("il2cpp_class_get_methods",class_methods); MAP("il2cpp_method_get_name",method_name);
    MAP("il2cpp_method_get_return_type",method_return_type);
    MAP("il2cpp_method_get_param_count",method_param_count);
    MAP("il2cpp_runtime_invoke",runtime_invoke); MAP("il2cpp_object_new",object_new);
    MAP("il2cpp_string_new",string_new); MAP("il2cpp_array_new",array_new);
    failed=1;return 0;
}
int main(void) {
    if(x2_open_save_manager(&login,0)!=1 || failed || invoked!=1)return 1;
    omit_symbol=1;
    if(x2_open_save_manager(&login,0)!=0 || invoked!=1)return 2;
    if(x2_open_save_manager(0,0)!=0)return 3;

    /* The trampoline entry point: board hero 1014 -> DubbingId 1351432, played
     * once per process even though MainAniEnter fires on every return to the hall. */
    omit_symbol=0;                       /* restore the full API for the title-voice case */
    method_cur_hero.entry=(void*)mock_get_cur_hero;
    method_all_dubbing.entry=(void*)mock_all_dubbing;
    method_play_voice.entry=(void*)mock_play_voice;
    dubbing_rows.head.max_length=dubbing_count;
    for(int i=0;i<dubbing_count;++i)dubbing_rows.values[i]=&dubbing_row[i];

    if(x2_play_login_title_voice(&login,0)!=1 || played_dubbing_id!=1351432)return 5;
    played_dubbing_id=0;
    if(x2_play_login_title_voice(&login,0)!=0 || played_dubbing_id!=0)return 6;
    return failed ? 4 : 0;
}
