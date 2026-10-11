/* Host-side contract test. Uses opaque managed strings, never C string casts. */
#include "x2save_bridge.c"

static int login, input_account, input_password, account_string, password_string;
static int url_string, open_string, class_string, domain, assembly, image;
static int input_class, game_class, ajc_class, object_class, login_class;
static int field_account, field_password, field_url, method_text, method_ctor;
static int method_generic, method_static, void_type, generic_type, ajc_object;
static int invoked, failed, omit_symbol;
static struct {struct Il2CppArrayHead head; void* values[3];} array;

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
    return 0;
}
static void* mock_object_class(void* p) {return p==&login ? &login_class : &input_class;}
static void* mock_class_parent(void* p) {return 0;}
static void* mock_field_from_name(void* p, const char* n) {
    if(name_is(n,"mTxtAccount"))return &field_account;
    if(name_is(n,"mTxtPassword"))return &field_password;
    if(name_is(n,"Login_Url"))return &field_url;
    return 0;
}
static void mock_field_get_value(void* p, void* f, void* out) {
    *(void**)out=f==&field_account ? &input_account : &input_password;
}
static void mock_field_static_get_value(void* f, void* out) {*(void**)out=&url_string;}
static void* mock_method_from_name(void* p, const char* n, int arity) {
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
    return failed ? 4 : 0;
}
