/* x2save_bridge.c - minimal save-manager entry bridge for X2 Revival.
 *
 * Loaded on demand by the patched login button trampoline inside libil2cpp.so:
 *   x2_open_save_manager(void* login_page, void* il2cpp)
 *
 * Reads the login form's account/password InputField text through the il2cpp
 * public C API, resolves the server base URL from GameConst.Login_Url, and
 * hands everything to com.siva.project.x2.SaveManagerBridge.open(...) on the
 * Java side (via UnityEngine.AndroidJavaClass, so this library never touches
 * JNI directly). Returns 1 when dispatched, 0 on bridge failure. The caller
 * must not fall back to guest login for a save-manager failure.
 *
 * Deliberately self-contained and dependency-light: no system headers (built
 * -nostdlib without a sysroot), only dlopen/dlsym which Android's runtime
 * linker resolves from the recorded DT_NEEDED libdl.so/libc.so entries. No
 * globals hold sensitive data; strings live transiently on the stack.
 */
typedef unsigned long      ulong_a;

extern void* dlopen(const char* filename, int flags);
extern void* dlsym(void* handle, const char* symbol);

typedef void* (*fn_domain_get)(void);
typedef void* (*fn_thread_attach)(void*);
typedef void* (*fn_class_from_name)(void*, const char*, const char*);
typedef void* (*fn_field_from_name)(void*, const char*);
typedef void  (*fn_field_static_get_value)(void*, void*);
typedef void  (*fn_field_get_value)(void*, void*, void*);
typedef void* (*fn_method_from_name)(void*, const char*, int);
typedef void* (*fn_runtime_invoke)(void*, void*, void**, void**);
typedef void* (*fn_string_new)(const char*);
typedef void* (*fn_object_new)(void*);
typedef void* (*fn_get_corlib)(void);
typedef void* (*fn_domain_assemblies)(void*, ulong_a*);
typedef void* (*fn_assembly_image)(void*);
typedef const char* (*fn_image_name)(void*);
typedef void* (*fn_class_parent)(void*);
typedef void* (*fn_object_class)(void*);
typedef void* (*fn_class_methods)(void*, void**);
typedef const char* (*fn_method_name)(void*);
typedef void* (*fn_method_return_type)(void*);
typedef int   (*fn_method_param_count)(void*);
typedef void* (*fn_array_new)(void*, ulong_a);

struct Il2CppArrayHead {
    void*     klass;
    void*     monitor;
    void*     bounds;
    ulong_a   max_length;
    void*     vector[];
};

struct Api {
    fn_domain_get          domain_get;
    fn_thread_attach       thread_attach;
    fn_class_from_name     class_from_name;
    fn_field_from_name     field_from_name;
    fn_field_static_get_value field_static_get_value;
    fn_field_get_value     field_get_value;
    fn_method_from_name    method_from_name;
    fn_runtime_invoke      runtime_invoke;
    fn_string_new          string_new;
    fn_object_new          object_new;
    fn_get_corlib          get_corlib;
    fn_domain_assemblies   domain_assemblies;
    fn_assembly_image      assembly_image;
    fn_image_name          image_name;
    fn_class_parent        class_parent;
    fn_object_class        object_class;
    fn_class_methods       class_methods;
    fn_method_name         method_name;
    fn_method_return_type  method_return_type;
    fn_method_param_count  method_param_count;
    fn_array_new           array_new;
};

#define SYM_AS(name, symbol) do { api->name = (void*)dlsym(h, symbol); if (!api->name) return 0; } while (0)
#define SYM(name) SYM_AS(name, "il2cpp_" #name)

/* Diagnostics contain stage names only, never credentials or tokens. */
static void diagnostic(const char* stage) {
    void* log = dlopen("liblog.so", 1);
    if (!log) return;
    int (*write_log)(int, const char*, const char*) =
        (void*)dlsym(log, "__android_log_write");
    if (write_log) write_log(4, "X2SaveManager", stage);
}

static int load_api(void* h, struct Api* api) {
    SYM(domain_get);
    SYM(thread_attach);
    SYM(class_from_name);
    SYM_AS(field_from_name, "il2cpp_class_get_field_from_name");
    SYM(field_static_get_value);
    SYM(field_get_value);
    SYM_AS(method_from_name, "il2cpp_class_get_method_from_name");
    SYM(runtime_invoke);
    SYM(string_new);
    SYM(object_new);
    SYM(get_corlib);
    SYM_AS(domain_assemblies, "il2cpp_domain_get_assemblies");
    SYM_AS(assembly_image, "il2cpp_assembly_get_image");
    SYM_AS(image_name, "il2cpp_image_get_name");
    SYM_AS(class_parent, "il2cpp_class_get_parent");
    SYM_AS(object_class, "il2cpp_object_get_class");
    SYM_AS(class_methods, "il2cpp_class_get_methods");
    SYM_AS(method_name, "il2cpp_method_get_name");
    SYM_AS(method_return_type, "il2cpp_method_get_return_type");
    SYM_AS(method_param_count, "il2cpp_method_get_param_count");
    SYM(array_new);
    return 1;
}

/* Find a class by namespace/name across every loaded image. */
static void* find_class(struct Api* api, const char* ns, const char* name) {
    ulong_a count = 0;
    void* domain = api->domain_get();
    void** assemblies = (void**)api->domain_assemblies(domain, &count);
    if (!assemblies) return 0;
    for (ulong_a i = 0; i < count; ++i) {
        void* image = api->assembly_image(assemblies[i]);
        if (!image) continue;
        void* cls = api->class_from_name(image, ns, name);
        if (cls) return cls;
    }
    return 0;
}

/* Keep Il2CppString objects intact. il2cpp_string_chars is UTF-16, not UTF-8. */
static void* read_input_text(struct Api* api, void* login_page, const char* field_name) {
    void* cls = api->object_class(login_page);
    void* field = api->field_from_name(cls, field_name);
    if (!field) return 0;
    void* input_field = 0;
    api->field_get_value(login_page, field, &input_field);
    if (!input_field) return 0;
    void* method = api->method_from_name(api->object_class(input_field), "get_text", 0);
    if (!method) return 0;
    void* exc = 0;
    void* str = api->runtime_invoke(method, input_field, 0, &exc);
    if (exc || !str) return 0;
    return str;
}

/* Static string field of a global-namespace class (GameConst.Login_Url). */
static void* read_static_string(struct Api* api, void* cls, const char* field_name) {
    if (!cls) return 0;
    void* field = api->field_from_name(cls, field_name);
    if (!field) return 0;
    void* str = 0;
    api->field_static_get_value(field, &str);
    if (!str) return 0;
    return str;
}

/* Prefix-free name compare (no strlen/strcmp available). */
static int name_is(const char* candidate, const char* wanted) {
    while (*wanted) {
        if (*candidate != *wanted) return 0;
        ++candidate; ++wanted;
    }
    return *candidate == 0;
}

/* Pick the void-returning CallStatic(string, object[]) overload on
 * AndroidJavaObject (AndroidJavaClass inherits it). Generic CallStatic<T>
 * inflations share the name and arity, so the return type must disambiguate:
 * any constructor's return type pointer is the interned System.Void type. */
static void* find_call_static(struct Api* api, void* ajc_class) {
    void* ctor = api->method_from_name(ajc_class, ".ctor", 1);
    if (!ctor) return 0;
    void* void_type = api->method_return_type(ctor);
    for (void* cls = ajc_class; cls; cls = api->class_parent(cls)) {
        void* iter = 0;
        void* method;
        while ((method = api->class_methods(cls, &iter)) != 0) {
            const char* name = api->method_name(method);
            if (!name) continue;
            if (name_is(name, "CallStatic") && api->method_param_count(method) == 2 &&
                    api->method_return_type(method) == void_type) {
                return method;
            }
        }
    }
    return 0;
}

int x2_open_save_manager(void* login_page, void* il2cpp);

int x2_open_save_manager(void* login_page, void* il2cpp) {
    struct Api api;
    if (!login_page) return 0;
    /* The trampoline's handle belongs to this bridge, not libil2cpp. */
    il2cpp = dlopen("libil2cpp.so", 1);
    if (!il2cpp || !load_api(il2cpp, &api)) {
        diagnostic("bridge: il2cpp API unavailable");
        return 0;
    }

    void* domain = api.domain_get();
    if (!domain) return 0;
    api.thread_attach(domain);

    void* account = read_input_text(&api, login_page, "mTxtAccount");
    void* password = read_input_text(&api, login_page, "mTxtPassword");
    if (!account || !password) {
        diagnostic("bridge: login input unavailable");
        return 0;
    }

    void* ajc_class = find_class(&api, "UnityEngine", "AndroidJavaClass");
    if (!ajc_class) return 0;
    void* game_const = find_class(&api, "", "GameConst");
    void* base_url = read_static_string(&api, game_const, "Login_Url");
    if (!base_url) return 0;

    void* call_static = find_call_static(&api, ajc_class);
    if (!call_static) return 0;

    void* exc = 0;
    void* cls_name_str = api.string_new("com.siva.project.x2.SaveManagerBridge");
    if (!cls_name_str) return 0;
    void* ajc = api.object_new(ajc_class);
    if (!ajc) return 0;
    {
        void* ctor = api.method_from_name(ajc_class, ".ctor", 1);
        void* args[1];
        args[0] = cls_name_str;
        api.runtime_invoke(ctor, ajc, args, &exc);
        if (exc) return 0;
    }

    void* object_class = api.class_from_name(api.get_corlib(), "System", "Object");
    if (!object_class) return 0;
    struct Il2CppArrayHead* jargs =
        (struct Il2CppArrayHead*)api.array_new(object_class, 3);
    if (!jargs || jargs->max_length != 3) return 0;
    jargs->vector[0] = account;
    jargs->vector[1] = password;
    jargs->vector[2] = base_url;

    void* invoke_args[2];
    invoke_args[0] = api.string_new("open");    /* methodName is not a Java argument */
    invoke_args[1] = (void*)jargs;               /* object[] args */
    api.runtime_invoke(call_static, ajc, invoke_args, &exc);
    if (exc) {
        diagnostic("bridge: Java invocation failed");
        return 0;
    }
    diagnostic("bridge: dialog dispatched");
    return 1;
}

/* ---------------------------------------------------------------------------
 * Login title voice
 * ---------------------------------------------------------------------------
 * Called by the MainAniEnter trampoline (patch_title_voice.py) at the moment
 * the player taps 开始跃迁: replays the board hero's 「标题」 dubbing line.
 *
 * Why the retail client keeps it silent: every hero owns a 标题 row in the
 * Dubbing table (DubbingName = 1350035, SoundID = heroId * 100 + 8) and the
 * audio bank ships in the package (e.g. Vo_JP_H1010_Logo.bank for ECLIPSE),
 * but none of the ten GameAPI.PlayVoice call sites covers "entered the main
 * hall", so the row stays locked in the voice archive.
 *
 * Everything is resolved by name - no RVA, no field offset - so this stays
 * valid across client builds:
 *   AccountInfoModule.get_CurHero()  -> board hero id (int32)
 *   DubbingManager.GetAllItem()      -> DubbingArray wrapper class
 *       -> .Items  (List<Dubbing>; .Keys sits at the same layout position!)
 *          -> _items[] rows, matched on (HeroId, DubbingName)
 *   GameAPI.PlayVoice(DubbingId)     -> FMOD; the bank is loaded inside
 *
 * These bodies never read `this` (the client itself calls them with x0 = 0),
 * so the methodPointer is called directly with a null receiver and a null
 * MethodInfo, exactly like the call sites in the game. Do not switch to
 * runtime_invoke here: it boxes the int32 return value, so get_CurHero would
 * hand back an Il2CppObject header instead of a hero id.
 *
 * Once per process: MainAniEnter runs on every return to the hall, only the
 * login one should speak.
 */

#define TITLE_DUBBING_NAME 1350035   /* Language row id of 标题 */

static int title_voice_played = 0;

/* MethodInfo::methodPointer is its first member: the native entry point. */
static void* method_entry(struct Api* api, void* cls, const char* name, int argc) {
    void* info = cls ? api->method_from_name(cls, name, argc) : 0;
    return info ? *(void**)info : 0;
}

static void* object_field(struct Api* api, void* obj, const char* field_name) {
    void* value = 0;
    if (!obj) return 0;
    void* field = api->field_from_name(api->object_class(obj), field_name);
    if (!field) return 0;
    api->field_get_value(obj, field, &value);
    return value;
}

static int int_field(struct Api* api, void* obj, const char* field_name, int* out) {
    void* field = obj ? api->field_from_name(api->object_class(obj), field_name) : 0;
    if (!field) return 0;
    api->field_get_value(obj, field, out);
    return 1;
}

/* (heroId, 标题) -> DubbingId, or 0 when the row is missing. */
static int find_title_dubbing(struct Api* api, int hero) {
    void* entry = method_entry(api, find_class(api, "", "DubbingManager"), "GetAllItem", 0);
    if (!entry) return 0;

    /* GetAllItem returns the wrapper class, whose .Items is the row list. */
    void* wrapper = ((void* (*)(void*, void*))entry)(0, 0);
    void* list = object_field(api, wrapper, "Items");
    if (!list) return 0;

    int size = 0;
    if (!int_field(api, list, "_size", &size) || size <= 0) return 0;
    struct Il2CppArrayHead* rows = (struct Il2CppArrayHead*)object_field(api, list, "_items");
    if (!rows || (int)rows->max_length < size) return 0;

    for (int i = 0; i < size; ++i) {
        void* row = rows->vector[i];
        int row_hero = 0;
        int row_name = 0;
        int row_id = 0;
        if (!row) continue;
        if (!int_field(api, row, "HeroId", &row_hero) || row_hero != hero) continue;
        if (!int_field(api, row, "DubbingName", &row_name) || row_name != TITLE_DUBBING_NAME) continue;
        if (!int_field(api, row, "DubbingId", &row_id)) continue;
        return row_id;
    }
    return 0;
}

int x2_play_login_title_voice(void* main_hall_fsm, void* il2cpp);

int x2_play_login_title_voice(void* main_hall_fsm, void* il2cpp) {
    struct Api api;
    (void)main_hall_fsm;
    il2cpp = il2cpp ? il2cpp : dlopen("libil2cpp.so", 1);   /* the trampoline passes its own handle */
    if (!load_api(il2cpp, &api)) {
        diagnostic("title voice: il2cpp API unavailable");
        return 0;
    }

    void* domain = api.domain_get();
    if (!domain) return 0;
    api.thread_attach(domain);
    if (title_voice_played) return 0;

    void* entry = method_entry(&api, find_class(&api, "", "AccountInfoModule"), "get_CurHero", 0);
    if (!entry) {
        diagnostic("title voice: get_CurHero unavailable");
        return 0;
    }
    int hero = ((int (*)(void*, void*))entry)(0, 0);
    if (hero <= 0) {
        diagnostic("title voice: no board hero");
        return 0;
    }

    int dubbing = find_title_dubbing(&api, hero);
    if (dubbing <= 0) {
        diagnostic("title voice: 标题 row not found");
        return 0;
    }

    entry = method_entry(&api, find_class(&api, "", "GameAPI"), "PlayVoice", 1);
    if (!entry) {
        diagnostic("title voice: PlayVoice unavailable");
        return 0;
    }
    title_voice_played = 1;   /* before the call: MainAniEnter may re-enter */
    ((void (*)(void*, int, void*))entry)(0, dubbing, 0);
    diagnostic("title voice: played");
    return 1;
}
