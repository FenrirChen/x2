"""Emulate the actual ARM64 patch bytes, including failure branches and ABI state."""
import json,sys
from pathlib import Path
R=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(R/'runtime/client_release20261024/deps'))
from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE
from unicorn import arm64_const as C


def validate(native,audit):
    data=Path(native).read_bytes();audit=json.loads(Path(audit).read_text(encoding='utf8'))['native']
    uc=Uc(UC_ARCH_ARM64,UC_MODE_ARM);uc.mem_map(0,(len(data)+4095)//4096*4096);uc.mem_write(0,data)
    uc.reg_write(C.UC_ARM64_REG_CPACR_EL1, 3 << 20)
    item=0x6000000;stack=0x70000000;uc.mem_map(item,4096);uc.mem_map(stack,0x20000)
    cave=audit['star_cave'];checked=0
    for kind in (10,11,36):
        uc.mem_write(item+0x24,kind.to_bytes(4,'little'))
        for star_index in (0,-1,-2,-3,-4):
            for roll in (1,127,128,129,383,384,385,386,38783,51199):
                uc.reg_write(C.UC_ARM64_REG_X19,item);uc.reg_write(C.UC_ARM64_REG_W26,star_index&0xffffffff);uc.reg_write(C.UC_ARM64_REG_W0,roll)
                uc.emu_start(cave,0x1e497dc,count=20)
                flags=uc.reg_read(C.UC_ARM64_REG_NZCV)
                actual=bool((flags>>31&1)!=(flags>>28&1))
                assert actual==(roll<(385 if kind==10 and star_index==0 else 129)),(kind,star_index,roll)
                checked+=1
    # Exactly min(3*p,1): retain the same random range rather than rounding
    # its denominator. These counts cover every possible native denominator.
    from fractions import Fraction
    for cap in range(2,51201):
        assert Fraction(min(384,cap-1),cap-1)==min(3*Fraction(min(128,cap-1),cap-1),1)
    voice_cave=audit['title_cave']
    dlopen,dlsym,bridge=0x113e820,0x113fa80,item+0x100
    for fail in ('none','dlopen','dlsym'):
        sp=stack+0x10000
        original={getattr(C,f'UC_ARM64_REG_X{i}'):0x120000+i*32 for i in range(31)}
        original.update({getattr(C,f'UC_ARM64_REG_Q{i}'):(i+17)*2**96+i for i in range(32)})
        original.update({C.UC_ARM64_REG_NZCV:0x60000000,C.UC_ARM64_REG_FPCR:0x400000,C.UC_ARM64_REG_FPSR:1})
        for reg,value in original.items():uc.reg_write(reg,value)
        uc.reg_write(C.UC_ARM64_REG_SP,sp)
        calls=[]
        def hook(machine,address,size,user):
            if address not in (dlopen,dlsym,bridge):return
            calls.append(address);lr=machine.reg_read(C.UC_ARM64_REG_LR)
            for i in range(18):machine.reg_write(getattr(C,f'UC_ARM64_REG_X{i}'),0xdead0000+i)
            for i in range(32):machine.reg_write(getattr(C,f'UC_ARM64_REG_Q{i}'),0x12345678+i)
            machine.reg_write(C.UC_ARM64_REG_NZCV,0x90000000);machine.reg_write(C.UC_ARM64_REG_FPCR,0);machine.reg_write(C.UC_ARM64_REG_FPSR,0)
            value=(0 if fail=='dlopen' else 0x1234) if address==dlopen else (0 if fail=='dlsym' else bridge)
            machine.reg_write(C.UC_ARM64_REG_X0,value);machine.reg_write(C.UC_ARM64_REG_PC,lr)
        handle=uc.hook_add(UC_HOOK_CODE,hook)
        try: uc.emu_start(voice_cave,0x13bda28,count=300)
        except Exception:
            print("EMU_FAILURE_PC",hex(uc.reg_read(C.UC_ARM64_REG_PC)),"calls",calls);raise
        uc.hook_del(handle)
        assert all(uc.reg_read(k)==v for k,v in original.items()),'register loss on '+fail
        assert uc.reg_read(C.UC_ARM64_REG_SP)==sp-32
        assert len(calls)=={'none':3,'dlopen':1,'dlsym':2}[fail]
    result={'quality_cases':checked,'probability_denominators':51199,'title_success_and_failure_abi_paths':3,'result':'passed'}
    print(json.dumps(result));return result


if __name__=='__main__':
    validate(*sys.argv[1:3])



