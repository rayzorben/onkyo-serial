from setuptools import setup

setup(name='onkyo_serial',
            version='0.0.1',
            description='Onkyo receiver control via RS232.',
            author='rayzorben',
            url='https://github.com/rayzorben/onkyo-serial',
            license='MIT',
            packages=['onkyo_serial'],
            install_requires=['pyserial==3.2.1'],
            zip_safe=False)